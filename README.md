# Estimation de cartes Pokémon

Script Python à lancer **une fois par achat** : il prend toutes les cartes du fichier JSON et sort un **classeur Excel** avec **un onglet par extension**.
Chaque carte y figure avec son **image**, son **prix** (tendance Cardmarket) et le **prix d'achat** à proposer.

Les prix viennent de l'API gratuite [TCGdex](https://tcgdex.dev), qui reprend les prix Cardmarket.
La tendance n'est **pas filtrée par langue** (toutes langues confondues). Un coefficient est ensuite appliqué selon l'état de la carte.

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
python estimation_cartes.py cartes.json               # tableau + estimation.xlsx
python estimation_cartes.py cartes.json -o lot.xlsx   # autre fichier de sortie
python estimation_cartes.py --extensions             # liste des extensions -> extensions.csv
python estimation_cartes.py cartes.json --rafraichir # recharge les extensions (nouvelle sortie)
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
- `etat` : `MT`, `NM`, `EX`, `GD`, `LP`, `PL`, `PO` (NM par défaut).
- `quantite` et `variante` (`normal`, `reverse`, `holo`) sont facultatifs.
  Pour une **reverse**, ajoutez `"variante": "reverse"` : le prix utilisé est alors la tendance reverse/holo de Cardmarket,
  et la carte apparaît comme « Nom (reverse) » dans l'Excel.

La liste `ar_alt_me.json` contient toutes les **AR** (Illustration rare) et **ALT** (Illustration spéciale rare)
du bloc Méga-Évolution, de MEG à PBL (156 cartes, en NM).

## Calcul

| Étape | Formule |
|---|---|
| Prix | tendance Cardmarket × coefficient d'état (NM 100 %, EX 85 %, GD 70 %, LP 60 %, PL 50 %, PO 30 %) |
| Prix d'achat | prix × 0,8, **arrondi au 0,50 € inférieur** (6,70 → 6,50 ; 6,40 → 6,00) |

Les coefficients (`COEF_ETAT`), la remise (`REMISE_ACHAT`) et le pas d'arrondi (`PAS_ARRONDI`)
se règlent en haut de `estimation_cartes.py`.

## Contenu du fichier Excel

- **Récapitulatif** : nombre de cartes, valeur et prix d'achat par série, et le total du lot.
- **Un onglet par série** (ex. « PFL - Flammes Fantasmagoriques ») : image de la carte, code, nom, état, quantité, tendance, **Prix FR**, prix retenu,
  prix d'achat, total et lien Cardmarket, avec une ligne de total en bas.

### Saisir le premier prix FR

Le lien **« Voir les offres FR »** ouvre la page Cardmarket de la carte, déjà filtrée sur les offres **en français**
dans l'état de la carte ou meilleur. Recopiez le premier prix dans la case jaune **Prix FR** :
le prix d'achat (−20 %, arrondi au 0,50 € inférieur), les totaux et le récapitulatif se recalculent dans Excel.
Si la case reste vide, le calcul utilise la tendance Cardmarket toutes langues.
- **Erreurs** (seulement s'il y en a) : cartes introuvables ou sans prix.

Certaines cartes promo n'ont pas d'image chez TCGdex : la case indique alors « (pas d'image) ».

## Utilisation dans une autre application

```python
from estimation_cartes import estimer
resultats, total_achat = estimer([{"carte": "PFL01", "etat": "NM"}])
```
