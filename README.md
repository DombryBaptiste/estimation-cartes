# Estimation de cartes Pokémon

Script Python qui transforme une liste de cartes (fichier JSON) en **classeur de sélection pour les achats**,
pensé pour être **importé dans Google Sheets** : un **onglet par série**, l'**image** de chaque carte,
une case **Prix FR** à remplir, le **prix d'achat** calculé automatiquement, une case **Pris** à cocher
et un **récapitulatif** qui ne totalise que les cartes prises.

Les fiches des cartes (nom, image, n° de produit Cardmarket) viennent de l'API gratuite [TCGdex](https://tcgdex.dev).

## Installation (une seule fois)

1. Installez **Python 3.10 ou plus récent** depuis https://www.python.org/downloads/
   en cochant **« Add python.exe to PATH »**.
2. Dans un terminal ouvert dans ce dossier, copiez-collez la commande suivante.
   Elle installe le module nécessaire (`openpyxl`) :

```bash
python -m pip install --upgrade -r requirements.txt
```

> En cas d'erreur `No module named openpyxl`, relancez l'installation : le module doit être installé
> pour **le même Python** que celui qui lance le script (d'où `python -m pip` plutôt que `pip`).

## Utilisation

```bash
python estimation_cartes.py cartes_eb01_30ans.json -o cartes_eb01_30ans.xlsx   # base complète (~2 min)
python estimation_cartes.py mon_achat.json                                     # votre liste -> estimation.xlsx
python estimation_cartes.py --extensions                                       # codes des extensions -> extensions.csv
python estimation_cartes.py mon_achat.json --rafraichir                        # recharge les extensions (nouvelle sortie)
```

Format du fichier JSON :

```json
[
  {"carte": "PFL01", "etat": "NM"},
  {"carte": "MEW 151", "etat": "EX", "quantite": 2},
  {"carte": "PFL-004", "etat": "NM", "variante": "reverse"}
]
```

- `carte` : code de l'extension + numéro (`PFL01`, `PFL 1`, `PFL-001`…). Les codes sont listés dans `extensions.csv`.
  Pour les sous-séries, utilisez le code complet suivi d'un espace : `BRS:TG TG13`, `SHF:SV SV001`, `CRZ:GG GG01`.
- `etat` : `MT`, `NM`, `EX`, `GD`, `LP`, `PL`, `PO` (NM par défaut). Le lien Cardmarket filtre sur cet état ou mieux.
- `quantite` (une ligne par exemplaire) et `variante` (`reverse`, `holo`) sont facultatifs.
  Une reverse apparaît comme « Nom (reverse) » ; sur Cardmarket, cochez le filtre « Reverse Holo » avant de relever le prix.

### Listes fournies

| Fichier | Contenu |
|---|---|
| `cartes_eb01_30ans.json` | **Toutes les cartes d'EB01 (Épée et Bouclier) au set des 30 ans**, galeries, coffre étincelant et Collection Classique comprises, **hors Commune, Peu Commune, Rare, Holo, ex classiques (Double rare) et V classiques** : 2 384 cartes, 47 séries. Promos et énergies exclues. |
| `rares_ev_me.json` | AR, Full Art, ALT et Gold du bloc Écarlate et Violet et du bloc Méga-Évolution : 1 169 cartes. |

Les raretés viennent de TCGdex. Exemples de raretés gardées : VMAX, VSTAR, Ultra Rare (Full Art), Illustration rare,
Illustration spéciale rare, Hyper rare, Chromatique, Radieux, Magnifique, HIGH-TECH (ACE SPEC), Galerie de dresseurs…

## Importer dans Google Sheets

1. Dans Google Drive : **Nouveau > Importer un fichier** et choisissez le `.xlsx`,
   puis ouvrez-le avec Google Sheets (ou, dans un Sheets vide : **Fichier > Importer > Importer > Remplacer la feuille de calcul**).
2. Les images s'affichent toutes seules (formule `=IMAGE()`), les liens Cardmarket aussi (`=HYPERLINK()`).
3. **Cases à cocher** : dans chaque onglet, sélectionnez la colonne **B (Pris)** à partir de B2, puis
   **Insertion > Case à cocher**. Les cellules valent déjà FAUX : elles deviennent des cases décochées.

## Utiliser la feuille

**Onglets de série** (ex. « PFL - Flammes Fantasmagoriques ») : Image, **Pris**, Carte, Nom, État,
**Prix FR** (case jaune), **Prix d'achat**, lien **Cardmarket FR**, et en bas le total des cartes prises.

1. Cliquez sur **« Voir les offres FR »** : la page Cardmarket s'ouvre filtrée sur les offres **en français**
   dans l'état de la carte ou mieux. Recopiez le premier prix dans la case jaune **Prix FR**.
2. Le **prix d'achat** se calcule : prix FR − 20 %, **arrondi au 0,50 € inférieur** (6,70 → 6,50 ; 6,40 → 6,00).
3. Cochez **Pris** pour chaque carte que vous prenez (ou tapez `x`) : la ligne passe en vert.

**Récapitulatif** : pour chaque série, le nombre de cartes prises, leur valeur (prix FR) et leur prix d'achat,
avec le **total général**. Seules les cartes cochées sont comptées.

**Remise à zéro** : dans chaque onglet, sélectionnez la colonne **B (Pris)** et appuyez sur **Suppr** (les cases se décochent).
Même chose sur la colonne **F (Prix FR)** pour effacer les prix.

La remise (`REMISE_ACHAT`) et le pas d'arrondi (`PAS_ARRONDI`) se règlent en haut de `estimation_cartes.py`.
