# Estimation de cartes Pokémon

Script Python qui transforme une liste de cartes (fichier JSON) en **classeur Excel de sélection pour les achats** :
un **onglet par série**, l'**image** de chaque carte, une case **Prix FR** à remplir, le **prix d'achat** calculé
automatiquement, une case **Pris** à cocher et un **récapitulatif** qui ne totalise que les cartes prises.

Les fiches des cartes (nom, image, n° de produit Cardmarket) viennent de l'API gratuite [TCGdex](https://tcgdex.dev).

## Installation (une seule fois)

1. Installez **Python 3.10 ou plus récent** depuis https://www.python.org/downloads/
   en cochant **« Add python.exe to PATH »**.
2. Dans un terminal ouvert dans ce dossier, copiez-collez la commande suivante.
   Elle installe les modules nécessaires (`openpyxl`, `pillow`) :

```bash
python -m pip install --upgrade -r requirements.txt
```

> En cas d'erreur `No module named openpyxl`, relancez l'installation : les modules doivent être installés
> pour **le même Python** que celui qui lance le script (d'où `python -m pip` plutôt que `pip`).

## Utilisation

```bash
python estimation_cartes.py rares_ev_me.json -o rares_ev_me.xlsx   # liste fournie (voir plus bas)
python estimation_cartes.py mon_achat.json                          # votre liste -> estimation.xlsx
python estimation_cartes.py --extensions                            # codes des extensions -> extensions.csv
python estimation_cartes.py mon_achat.json --rafraichir             # recharge les extensions (nouvelle sortie)
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
- `etat` : `MT`, `NM`, `EX`, `GD`, `LP`, `PL`, `PO` (NM par défaut). Le lien Cardmarket filtre sur cet état ou mieux.
- `quantite` (une ligne par exemplaire dans l'Excel) et `variante` (`reverse`, `holo`) sont facultatifs.
  Une reverse apparaît comme « Nom (reverse) » ; sur Cardmarket, cochez le filtre « Reverse Holo » avant de relever le prix.

### Liste fournie : `rares_ev_me.json`

Toutes les **AR**, **Full Art**, **ALT** et **Gold** du bloc Écarlate et Violet (SVI à BLK/WHT)
et du bloc Méga-Évolution (MEG à PBL), en NM : **1 169 cartes**, 22 séries.

| Catégorie | Raretés TCGdex |
|---|---|
| AR | Illustration rare |
| Full Art | Ultra Rare, Chromatique ultra rare (Destinées de Paldea) |
| ALT | Illustration spéciale rare |
| Gold | Hyper rare, Méga Hyper Rare, Rare Noir Blanc (Foudre Noire / Flamme Blanche) |

## Le fichier Excel

**Onglets de série** (ex. « PFL - Flammes Fantasmagoriques ») : Image, **Pris**, Carte, Nom, État,
**Prix FR** (case jaune), **Prix d'achat**, lien **Cardmarket FR**, et en bas le total des cartes prises.

1. Cliquez sur **« Voir les offres FR »** : la page Cardmarket s'ouvre filtrée sur les offres **en français**
   dans l'état de la carte ou mieux. Recopiez le premier prix dans la case jaune **Prix FR**.
2. Le **prix d'achat** se calcule : prix FR − 20 %, **arrondi au 0,50 € inférieur** (6,70 → 6,50 ; 6,40 → 6,00).
3. Dans **Pris**, choisissez ✔ dans la liste (ou tapez `x`) pour chaque carte que vous prenez : la ligne passe en vert.
   Avec Microsoft 365, vous pouvez aussi transformer la colonne en vraies cases à cocher (Insertion > Case à cocher).

**Récapitulatif** : pour chaque série, le nombre de cartes prises, leur valeur (prix FR) et leur prix d'achat,
avec le **total général**. Seules les cartes cochées « Pris » sont comptées.

**Remise à zéro** : cliquez sur le premier onglet de série, puis **Maj + clic** sur le dernier (les feuilles sont groupées),
sélectionnez la colonne **B (Pris)** et appuyez sur **Suppr**. Même chose sur la colonne **F (Prix FR)** pour effacer les prix.
Cliquez ensuite sur l'onglet Récapitulatif pour dégrouper les feuilles.

La remise (`REMISE_ACHAT`) et le pas d'arrondi (`PAS_ARRONDI`) se règlent en haut de `estimation_cartes.py`.
