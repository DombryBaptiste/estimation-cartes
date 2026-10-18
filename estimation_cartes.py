"""
Estimation d'un achat de cartes Pokémon : à lancer une fois par achat, sur la liste des cartes.

Classeur Excel : un onglet par extension, avec pour chaque carte son image, son prix et le prix d'achat :
- prix         = tendance Cardmarket × coefficient d'état (voir COEF_ETAT) ;
- prix d'achat = prix − REMISE_ACHAT (20 %), arrondi au 0,50 € inférieur (6,70 -> 6,50 ; 6,40 -> 6,00).
Dans Excel, la colonne « Prix FR » (jaune) permet de saisir le premier prix FR relevé via le lien
Cardmarket (déjà filtré sur le français et l'état) : le prix d'achat est alors recalculé sur ce prix.

Source : API gratuite TCGdex (https://tcgdex.dev), qui reprend la tendance Cardmarket
(toutes langues confondues).

Utilisation :
    python estimation_cartes.py cartes.json              -> tableau + estimation.xlsx
    python estimation_cartes.py cartes.json -o lot.xlsx
    python estimation_cartes.py cartes.json --rafraichir  (recharge la liste des sets)
    python estimation_cartes.py --extensions             -> extensions.csv (tous les codes)

Format du JSON :
    [
      {"carte": "PFL01", "etat": "NM"},
      {"carte": "MEW 151", "etat": "EX", "quantite": 2},
      {"carte": "PFL-004", "etat": "NM", "variante": "reverse"}
    ]

Intégration dans une autre application :
    from estimation_cartes import estimer
    resultats, total_achat = estimer([{"carte": "PFL01", "etat": "NM"}])
"""

import argparse
import csv
import json
import math
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = "https://api.tcgdex.net/v2"
CACHE_SETS = Path(__file__).with_name("sets_cache.json")

# Coefficient appliqué au prix Cardmarket (qui correspond en pratique à du NM).
COEF_ETAT = {
    "MT": 1.00,  # Mint
    "NM": 1.00,  # Near Mint
    "EX": 0.85,  # Excellent
    "GD": 0.70,  # Good
    "LP": 0.60,  # Light Played
    "PL": 0.50,  # Played
    "PO": 0.30,  # Poor
}

# Remise appliquée au prix pour obtenir le prix d'achat (0.20 = -20 %).
REMISE_ACHAT = 0.20

# Le prix d'achat est arrondi au multiple inférieur de ce pas (0.5 = au 0,50 € inférieur).
PAS_ARRONDI = 0.5

_set_cache = {}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "estimation-cartes/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def charger_codes_sets(rafraichir=False):
    """Associe les codes de sets (PFL, MEW, ...) aux identifiants TCGdex (me02, sv03.5, ...)."""
    if CACHE_SETS.exists() and not rafraichir:
        return json.loads(CACHE_SETS.read_text(encoding="utf-8"))

    print("Chargement de la liste des sets (une seule fois, mise en cache)...", file=sys.stderr)
    ids = [s["id"] for s in _get(f"{API}/en/sets")]
    with ThreadPoolExecutor(max_workers=16) as pool:
        details = list(pool.map(lambda i: _get(f"{API}/en/sets/{i}"), ids))

    codes = {}
    for d in details:
        if not d:
            continue
        codes[d["id"].upper()] = d["id"]
        abbr = d.get("abbreviation") or {}
        for code in (abbr.get("official"), abbr.get("localized")):
            if code:
                codes.setdefault(code.upper(), d["id"])
    CACHE_SETS.write_text(json.dumps(codes, indent=1, sort_keys=True), encoding="utf-8")
    return codes


def lister_extensions(chemin):
    """Écrit la liste des extensions (nom FR, code, date de sortie) dans un CSV, de la plus récente à la plus ancienne."""
    print("Chargement de toutes les extensions...", file=sys.stderr)
    noms_fr = {s["id"]: s["name"] for s in _get(f"{API}/fr/sets")}
    ids = [s["id"] for s in _get(f"{API}/en/sets")]
    with ThreadPoolExecutor(max_workers=16) as pool:
        details = [d for d in pool.map(lambda i: _get(f"{API}/en/sets/{i}"), ids)
                   if d and (d.get("serie") or {}).get("id") != "tcgp"]  # on ignore le jeu mobile TCG Pocket

    details.sort(key=lambda d: d.get("releaseDate") or "", reverse=True)
    with open(chemin, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["code", "nom_fr", "nom_en", "serie", "date_sortie", "nb_cartes", "id_tcgdex"])
        for d in details:
            abbr = d.get("abbreviation") or {}
            w.writerow([abbr.get("official", ""), noms_fr.get(d["id"], ""), d.get("name", ""),
                        (d.get("serie") or {}).get("name", ""), d.get("releaseDate", ""),
                        (d.get("cardCount") or {}).get("official", ""), d["id"]])
    print(f"{len(details)} extensions exportées dans {chemin}")


def decouper_code(code):
    """'PFL01' -> ('PFL', '01') ; 'MEW 151' -> ('MEW', '151') ; 'me02-004' -> ('ME02', '004')."""
    code = code.strip().upper()
    m = re.match(r"^(.+?)[\s\-_/#]+(\w+)$", code) or re.match(r"^([A-Z][A-Z0-9.]*?)(\d+[A-Z]?)$", code)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def _detail_set(set_id, langue):
    cle = (set_id, langue)
    if cle not in _set_cache:
        _set_cache[cle] = _get(f"{API}/{langue}/sets/{set_id}")
    return _set_cache[cle]


def trouver_carte(set_id, numero):
    """Renvoie la fiche TCGdex de la carte (en français si possible, sinon en anglais)."""
    for langue in ("fr", "en"):
        detail = _detail_set(set_id, langue)
        if not detail:
            continue
        for c in detail.get("cards", []):
            lid = c["localId"]
            if lid.upper() == numero or (lid.isdigit() and numero.isdigit() and int(lid) == int(numero)):
                return _get(f"{API}/{langue}/cards/{c['id']}")
    return None


def prix_tendance(fiche, variante):
    """Prix de tendance Cardmarket (normal, ou holo/reverse selon la variante)."""
    cm = (fiche.get("pricing") or {}).get("cardmarket") or {}
    if variante in ("reverse", "holo"):
        tendance = cm.get("trend-holo") or cm.get("trend")  # pas de prix holo : prix normal
    else:
        tendance = cm.get("trend") or cm.get("trend-holo")  # carte uniquement holo
    return tendance or None, cm.get("idProduct")


def arrondi_inferieur(prix, pas=PAS_ARRONDI):
    """Arrondi au multiple inférieur du pas : 6.7 -> 6.5 ; 6.4 -> 6.0 ; 6.5 -> 6.5."""
    return math.floor(prix / pas + 1e-9) * pas  # 1e-9 : évite 6.5 -> 6.0 à cause des flottants


def _valeur(entree, *cles, defaut=None):
    for k, v in entree.items():
        if k.lower() in cles:
            return v
    return defaut


def estimer_une(entree, codes):
    code = str(_valeur(entree, "carte", "card", "code", defaut="")).strip()
    etat = str(_valeur(entree, "etat", "état", "condition", defaut="NM")).strip().upper()
    quantite = int(_valeur(entree, "quantite", "quantité", "qte", "qty", defaut=1))
    variante = str(_valeur(entree, "variante", "variant", defaut="normal")).strip().lower()

    res = {"carte": code, "etat": etat, "quantite": quantite, "variante": variante,
           "nom": "", "extension": "", "image": "", "tendance": None, "prix": None,
           "prix_achat": None, "total_achat": None, "erreur": ""}

    prefixe, numero = decouper_code(code)
    set_id = codes.get(prefixe or "")
    if not set_id:
        res["erreur"] = f"code de set inconnu : {prefixe or code}"
        return res
    if etat not in COEF_ETAT:
        res["erreur"] = f"état inconnu : {etat} (attendu : {', '.join(COEF_ETAT)})"
        return res

    fiche = trouver_carte(set_id, numero)
    if not fiche:
        res["erreur"] = f"carte introuvable : {set_id} n°{numero}"
        return res

    res["nom"] = fiche.get("name", "") + (f" ({variante})" if variante in ("reverse", "holo") else "")
    res["extension"] = (fiche.get("set") or {}).get("name", "")
    # Série = extension précise (PFL - Flammes Fantasmagoriques), pas le bloc (Méga-Évolution).
    code_serie = ((_detail_set(set_id, "en") or {}).get("abbreviation") or {}).get("official") or prefixe
    res["serie"] = f"{code_serie} - {res['extension']}"
    if fiche.get("image"):
        res["image"] = fiche["image"] + "/high.png"
    tendance, id_cardmarket = prix_tendance(fiche, variante)
    if id_cardmarket:
        # Page produit filtrée sur les offres en français (language=2) et sur l'état demandé ou meilleur.
        res["lien"] = (f"https://www.cardmarket.com/fr/Pokemon/Products?idProduct={id_cardmarket}"
                       f"&language=2&minCondition={list(COEF_ETAT).index(etat) + 1}")
    if tendance is None:
        res["erreur"] = "pas de prix Cardmarket"
        return res
    res["tendance"] = tendance
    res["prix"] = round(tendance * COEF_ETAT[etat], 2)
    res["prix_achat"] = arrondi_inferieur(res["prix"] * (1 - REMISE_ACHAT))
    res["total_achat"] = res["prix_achat"] * quantite
    return res


def estimer(cartes, rafraichir=False):
    """Estime une liste de cartes. Renvoie (liste de résultats, total d'achat en EUR)."""
    codes = charger_codes_sets(rafraichir)
    with ThreadPoolExecutor(max_workers=8) as pool:
        resultats = list(pool.map(lambda e: estimer_une(e, codes), cartes))
    total = round(sum(r["total_achat"] or 0 for r in resultats), 2)
    return resultats, total


def _eur(v):
    return "-" if v is None else f"{v:.2f} €".replace(".", ",")


def afficher(resultats, total):
    lignes = [("Carte", "Nom", "État", "Qté", "Prix", "Prix d'achat", "Total achat")]
    for r in resultats:
        if r["erreur"]:
            lignes.append((r["carte"], "⚠ " + r["erreur"], r["etat"], str(r["quantite"]), "", "", ""))
        else:
            lignes.append((r["carte"], r["nom"][:30], r["etat"], str(r["quantite"]), _eur(r["prix"]),
                           _eur(r["prix_achat"]), _eur(r["total_achat"])))
    largeurs = [max(len(l[i]) for l in lignes) for i in range(len(lignes[0]))]
    for n, l in enumerate(lignes):
        print("  ".join(c.ljust(w) for c, w in zip(l, largeurs)))
        if n == 0:
            print("  ".join("-" * w for w in largeurs))
    nb_erreurs = sum(1 for r in resultats if r["erreur"])
    total_prix = sum((r["prix"] or 0) * r["quantite"] for r in resultats)
    print(f"\nValeur du lot : {_eur(total_prix)}")
    print(f"PRIX D'ACHAT  : {_eur(total)}  ({len(resultats) - nb_erreurs} cartes estimées, {nb_erreurs} en erreur)")


def _telecharger_image(url):
    """Image de la carte (petite taille) en mémoire, ou None si indisponible."""
    if not url:
        return None
    req = urllib.request.Request(url.replace("/high.png", "/low.png"), headers={"User-Agent": "estimation-cartes/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()
    except (urllib.error.URLError, TimeoutError):
        return None


def _nom_onglet(nom, deja_pris):
    """Nom d'onglet Excel valide (31 caractères max, sans []:*?/\\) et unique."""
    base = re.sub(r"[\[\]:*?/\\]", "-", nom or "Sans extension").strip()[:31] or "Sans extension"
    nom_final, n = base, 2
    while nom_final.lower() in deja_pris:
        suffixe = f" ({n})"
        nom_final, n = base[:31 - len(suffixe)] + suffixe, n + 1
    deja_pris.add(nom_final.lower())
    return nom_final


def exporter_excel(resultats, chemin):
    """Classeur Excel : un onglet par extension (avec l'image de chaque carte) + un onglet récapitulatif."""
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as ImageXL
    from openpyxl.styles import Alignment, Font, PatternFill

    EUR = '#,##0.00 "€"'
    LARGEUR_IMAGE, HAUTEUR_IMAGE = 90, 125  # pixels
    entete_style = (Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="3949AB"))

    def entete(ws, titres, largeurs):
        ws.append(titres)
        for cellule, largeur in zip(ws[ws.max_row], largeurs):
            cellule.font, cellule.fill = entete_style
            ws.column_dimensions[cellule.column_letter].width = largeur
        ws.freeze_panes = "A2"

    print("Téléchargement des images...", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=8) as pool:
        images = list(pool.map(lambda r: _telecharger_image(r.get("image")), resultats))

    # Regroupement par série (extension), dans l'ordre d'apparition dans le JSON.
    par_extension = {}
    for r, img in zip(resultats, images):
        if not r["erreur"]:
            par_extension.setdefault(r.get("serie") or "Sans série", []).append((r, img))

    wb = Workbook()
    recap = wb.active
    recap.title = "Récapitulatif"
    entete(recap, ["Série", "Cartes", "Valeur", "Prix d'achat"], [40, 10, 14, 14])

    # Prix d'achat calculé par Excel : il se met à jour quand on saisit le prix FR relevé sur Cardmarket.
    formule_achat = "=FLOOR(H{n}*" + f"{1 - REMISE_ACHAT:g}," + f"{PAS_ARRONDI:g})"
    saisie = PatternFill("solid", fgColor="FFF59D")

    onglets = {"récapitulatif", "erreurs"}
    for extension, lignes in par_extension.items():
        nom_onglet = _nom_onglet(extension, onglets)
        ws = wb.create_sheet(nom_onglet)
        entete(ws, ["Image", "Carte", "Nom", "État", "Qté", "Tendance", "Prix FR", "Prix retenu", "Prix d'achat",
                    "Total achat", "Cardmarket FR"],
               [14, 10, 30, 7, 6, 12, 12, 13, 13, 13, 16])
        ws["G1"].fill = PatternFill("solid", fgColor="F9A825")
        for r, img in lignes:
            n = ws.max_row + 1
            ws.append([None, r["carte"], r["nom"], r["etat"], r["quantite"], r["prix"], None,
                       f'=IF(G{n}="",F{n},G{n})', formule_achat.format(n=n), f"=I{n}*E{n}",
                       "Voir les offres FR" if r.get("lien") else None])
            ws.row_dimensions[n].height = HAUTEUR_IMAGE * 0.75 + 4  # points = pixels × 0,75
            for cellule in ws[n]:
                cellule.alignment = Alignment(vertical="center")
            for col in "FGHIJ":
                ws[f"{col}{n}"].number_format = EUR
            ws[f"G{n}"].fill = saisie
            if r.get("lien"):
                ws[f"K{n}"].hyperlink = r["lien"]
                ws[f"K{n}"].style = "Hyperlink"
                ws[f"K{n}"].alignment = Alignment(vertical="center")
            if img:
                image = ImageXL(BytesIO(img))
                image.width, image.height = LARGEUR_IMAGE, HAUTEUR_IMAGE
                ws.add_image(image, f"A{n}")
            else:
                ws[f"A{n}"] = "(pas d'image)"

        derniere = ws.max_row
        total = derniere + 1
        ws.append([None, None, "TOTAL", None, f"=SUM(E2:E{derniere})", None, None,
                   f"=SUMPRODUCT(E2:E{derniere},H2:H{derniere})", None, f"=SUM(J2:J{derniere})"])
        for cellule in ws[total]:
            cellule.font = Font(bold=True)
        ws[f"H{total}"].number_format = ws[f"J{total}"].number_format = EUR

        ref = "'" + nom_onglet.replace("'", "''") + "'!"
        recap.append([extension, f"={ref}E{total}", f"={ref}H{total}", f"={ref}J{total}"])

    derniere = recap.max_row
    recap.append(["TOTAL", f"=SUM(B2:B{derniere})", f"=SUM(C2:C{derniere})", f"=SUM(D2:D{derniere})"])
    for cellule in recap[recap.max_row]:
        cellule.font = Font(bold=True)
    for ligne in range(2, recap.max_row + 1):
        recap[f"C{ligne}"].number_format = recap[f"D{ligne}"].number_format = EUR
    recap.append([])
    recap.append(["Saisissez le premier prix FR (case jaune) dans chaque onglet : le prix d'achat et les totaux "
                  "se recalculent. Case vide = tendance Cardmarket toutes langues."])

    erreurs = [r for r in resultats if r["erreur"]]
    if erreurs:
        ws = wb.create_sheet("Erreurs")
        entete(ws, ["Carte", "État", "Qté", "Erreur"], [12, 7, 6, 60])
        for r in erreurs:
            ws.append([r["carte"], r["etat"], r["quantite"], r["erreur"]])

    wb.save(chemin)


def main():
    p = argparse.ArgumentParser(description="Estimation d'un achat de cartes Pokémon (prix Cardmarket, prix d'achat).")
    p.add_argument("fichier", nargs="?", help="fichier JSON contenant la liste des cartes")
    p.add_argument("-o", "--sortie", default="estimation.xlsx", help="fichier Excel de sortie")
    p.add_argument("--rafraichir", action="store_true", help="recharger la liste des sets (nouvelle extension)")
    p.add_argument("--extensions", action="store_true", help="exporter la liste des extensions dans extensions.csv")
    args = p.parse_args()

    if args.extensions:
        lister_extensions("extensions.csv")
        return
    if not args.fichier:
        p.error("indique un fichier JSON (ou --extensions)")

    cartes = json.loads(Path(args.fichier).read_text(encoding="utf-8"))
    resultats, total = estimer(cartes, args.rafraichir)
    afficher(resultats, total)
    exporter_excel(resultats, args.sortie)
    print(f"Détail exporté dans {args.sortie}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    main()
