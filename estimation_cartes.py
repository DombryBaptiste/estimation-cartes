"""
Classeur Excel de sélection pour les achats de cartes Pokémon.

Un onglet par série (ex. « PFL - Flammes Fantasmagoriques ») avec, pour chaque carte du JSON :
image, case « Pris », code, nom, état, prix FR à saisir, prix d'achat calculé et lien Cardmarket
(déjà filtré sur les offres en français et l'état).
- prix d'achat = prix FR − REMISE_ACHAT (20 %), arrondi au 0,50 € inférieur (6,70 -> 6,50 ; 6,40 -> 6,00) ;
- le récapitulatif ne totalise que les cartes cochées « Pris ».

Source des fiches (nom, image, n° Cardmarket) : API gratuite TCGdex (https://tcgdex.dev).

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
    if tendance is None:  # la carte reste listée : le prix FR se saisit dans l'Excel
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


def afficher(resultats):
    """Résumé console : nombre de cartes par série et cartes en erreur."""
    series = {}
    for r in resultats:
        if not r["erreur"]:
            series[r["serie"]] = series.get(r["serie"], 0) + r["quantite"]
    for serie, nb in series.items():
        print(f"  {nb:4d}  {serie}")
    erreurs = [r for r in resultats if r["erreur"]]
    for r in erreurs:
        print(f"  ⚠ {r['carte']} : {r['erreur']}")
    print(f"\n{sum(series.values())} cartes dans {len(series)} séries, {len(erreurs)} en erreur")


def _telecharger_image(url):
    """Vignette JPEG de la carte (180 × 250 px), ou None si indisponible."""
    if not url:
        return None
    from io import BytesIO
    from PIL import Image
    req = urllib.request.Request(url.replace("/high.png", "/low.jpg"), headers={"User-Agent": "estimation-cartes/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            image = Image.open(BytesIO(r.read())).convert("RGB")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    image.thumbnail((180, 250))
    sortie = BytesIO()
    image.save(sortie, "JPEG", quality=85)
    return sortie.getvalue()


def _nom_onglet(nom, deja_pris):
    """Nom d'onglet Excel valide (31 caractères max, sans []:*?/\\) et unique."""
    base = re.sub(r"[\[\]:*?/\\]", "-", nom or "Sans série").strip()[:31] or "Sans série"
    nom_final, n = base, 2
    while nom_final.lower() in deja_pris:
        suffixe = f" ({n})"
        nom_final, n = base[:31 - len(suffixe)] + suffixe, n + 1
    deja_pris.add(nom_final.lower())
    return nom_final


def exporter_excel(resultats, chemin):
    """
    Classeur Excel de sélection : un onglet par série, prix FR saisis à la main,
    case « Pris » par carte et récapitulatif des seules cartes prises.
    """
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as ImageXL
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    EUR = '#,##0.00 "€"'
    LARGEUR_IMAGE, HAUTEUR_IMAGE = 90, 125  # pixels
    entete_style = (Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="3949AB"))
    saisie = PatternFill("solid", fgColor="FFF59D")
    vert = PatternFill("solid", fgColor="C8E6C9")
    gras = Font(bold=True)

    def entete(ws, titres, largeurs):
        ws.append(titres)
        for cellule, largeur in zip(ws[ws.max_row], largeurs):
            cellule.font, cellule.fill = entete_style
            ws.column_dimensions[cellule.column_letter].width = largeur

    print("Téléchargement des images...", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=8) as pool:
        images = list(pool.map(lambda r: _telecharger_image(r.get("image")), resultats))

    # Regroupement par série, dans l'ordre du JSON ; une ligne par exemplaire.
    par_serie = {}
    for r, img in zip(resultats, images):
        if not r["erreur"]:
            par_serie.setdefault(r.get("serie") or "Sans série", []).extend([(r, img)] * max(1, r["quantite"]))

    wb = Workbook()
    recap = wb.active
    recap.title = "Récapitulatif"

    # Prix d'achat : prix FR saisi − remise, arrondi au pas inférieur ; vide tant que le prix n'est pas saisi.
    achat = '=IF(F{n}="","",FLOOR(F{n}*' + f"{1 - REMISE_ACHAT:g},{PAS_ARRONDI:g}))"
    # Carte prise : ✔ (liste), x, ou case à cocher Excel (VRAI).
    pris = '=IF(OR(B{n}=TRUE,B{n}="✔",LOWER(B{n})="x"),1,0)'

    onglets = {"récapitulatif", "erreurs"}
    lignes_recap = []
    for serie, cartes in par_serie.items():
        nom_onglet = _nom_onglet(serie, onglets)
        ws = wb.create_sheet(nom_onglet)
        entete(ws, ["Image", "Pris", "Carte", "Nom", "État", "Prix FR", "Prix d'achat", "Cardmarket FR", "pris"],
               [14, 7, 10, 32, 7, 12, 13, 18, 5])
        ws["F1"].fill = PatternFill("solid", fgColor="F9A825")
        ws.column_dimensions["I"].hidden = True  # colonne technique : 1 si la carte est prise
        ws.freeze_panes = "C2"

        for r, img in cartes:
            n = ws.max_row + 1
            ws.append([None, None, r["carte"], r["nom"], r["etat"], None, achat.format(n=n),
                       "Voir les offres FR" if r.get("lien") else None, pris.format(n=n)])
            ws.row_dimensions[n].height = HAUTEUR_IMAGE * 0.75 + 4  # points = pixels × 0,75
            for cellule in ws[n]:
                cellule.alignment = Alignment(vertical="center")
            ws[f"B{n}"].alignment = Alignment(horizontal="center", vertical="center")
            ws[f"B{n}"].font = Font(size=16, bold=True, color="2E7D32")
            ws[f"F{n}"].fill = saisie
            ws[f"F{n}"].number_format = ws[f"G{n}"].number_format = EUR
            if r.get("lien"):
                ws[f"H{n}"].hyperlink = r["lien"]
                ws[f"H{n}"].style = "Hyperlink"
                ws[f"H{n}"].alignment = Alignment(vertical="center")
            if img:
                image = ImageXL(BytesIO(img))
                image.width, image.height = LARGEUR_IMAGE, HAUTEUR_IMAGE
                ws.add_image(image, f"A{n}")
            else:
                ws[f"A{n}"] = "(pas d'image)"

        derniere = ws.max_row
        validation = DataValidation(type="list", formula1='"✔"', allow_blank=True, showErrorMessage=False)
        ws.add_data_validation(validation)
        validation.add(f"B2:B{derniere}")
        ws.conditional_formatting.add(f"B2:H{derniere}", FormulaRule(formula=["$I2=1"], fill=vert))

        total = derniere + 2
        ws[f"D{total}"] = "Cartes prises"
        ws[f"E{total}"] = f"=SUM(I2:I{derniere})"
        ws[f"F{total}"] = f"=SUMIF(I2:I{derniere},1,F2:F{derniere})"
        ws[f"G{total}"] = f"=SUMIF(I2:I{derniere},1,G2:G{derniere})"
        for col in "DEFG":
            ws[f"{col}{total}"].font = gras
        ws[f"F{total}"].number_format = ws[f"G{total}"].number_format = EUR

        ref = "'" + nom_onglet.replace("'", "''") + "'!"
        lignes_recap.append((serie, f"={ref}E{total}", f"={ref}F{total}", f"={ref}G{total}"))

    # Récapitulatif : uniquement les cartes prises.
    recap["A1"] = "Cartes prises"
    recap["A1"].font = Font(bold=True, size=14)
    recap.append([])
    entete(recap, ["Série", "Cartes prises", "Valeur (prix FR)", "Prix d'achat"], [40, 14, 16, 16])
    debut = recap.max_row + 1
    for ligne in lignes_recap:
        recap.append(list(ligne))
    fin = recap.max_row
    recap.append(["TOTAL", f"=SUM(B{debut}:B{fin})", f"=SUM(C{debut}:C{fin})", f"=SUM(D{debut}:D{fin})"])
    for cellule in recap[recap.max_row]:
        cellule.font = gras
    for ligne in range(debut, recap.max_row + 1):
        recap[f"C{ligne}"].number_format = recap[f"D{ligne}"].number_format = EUR
    # Séries avec des cartes prises en vert, les autres grisées.
    recap.conditional_formatting.add(f"A{debut}:D{fin}", FormulaRule(formula=[f"$B{debut}>0"], fill=vert))
    recap.conditional_formatting.add(f"A{debut}:D{fin}",
                                     FormulaRule(formula=[f"$B{debut}=0"], font=Font(color="BDBDBD")))

    aide = [
        "Mode d'emploi",
        "1. Dans chaque onglet, saisissez le prix FR (case jaune) : le prix d'achat se calcule (−20 %, arrondi au 0,50 € inférieur).",
        "2. Cochez « Pris » (liste ✔, ou tapez x) pour les cartes que vous prenez : la ligne passe en vert.",
        "3. Ce récapitulatif ne totalise que les cartes prises.",
        "Remise à zéro : cliquez sur le 1er onglet de série, puis Maj+clic sur le dernier (toutes les séries sont groupées),",
        "sélectionnez la colonne B (Pris) et appuyez sur Suppr. Même chose sur la colonne F pour effacer les prix.",
        "Cliquez ensuite sur l'onglet Récapitulatif pour dégrouper les feuilles.",
    ]
    recap.append([])
    for texte in aide:
        recap.append([texte])
    recap[f"A{recap.max_row - len(aide) + 1}"].font = gras

    erreurs = [r for r in resultats if r["erreur"]]
    if erreurs:
        ws = wb.create_sheet("Erreurs")
        entete(ws, ["Carte", "État", "Erreur"], [12, 7, 60])
        for r in erreurs:
            ws.append([r["carte"], r["etat"], r["erreur"]])

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
    resultats, _ = estimer(cartes, args.rafraichir)
    afficher(resultats)
    exporter_excel(resultats, args.sortie)
    print(f"Détail exporté dans {args.sortie}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    main()
