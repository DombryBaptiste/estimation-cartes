# Estimation de cartes Pokémon

Script Python à lancer **une fois par achat** : il prend toutes les cartes du fichier JSON et sort un CSV avec,
pour chaque carte, son **image**, son **prix** (tendance Cardmarket) et le **prix d'achat** à proposer.

Les prix viennent de l'API gratuite [TCGdex](https://tcgdex.dev), qui reprend les prix Cardmarket.
La tendance n'est **pas filtrée par langue** (toutes langues confondues). Un coefficient est ensuite appliqué selon l'état de la carte.

## Prérequis

Python 3.10 ou plus récent. Aucune dépendance à installer.

## Utilisation

```bash
python estimation_cartes.py cartes.json              # tableau + estimation.csv (image, prix, prix d'achat)
python estimation_cartes.py cartes.json -o lot.csv   # autre fichier de sortie
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

## Calcul

| Étape | Formule |
|---|---|
| Prix | tendance Cardmarket × coefficient d'état (NM 100 %, EX 85 %, GD 70 %, LP 60 %, PL 50 %, PO 30 %) |
| Prix d'achat | prix × 0,8, **arrondi au 0,50 € inférieur** (6,70 → 6,50 ; 6,40 → 6,00) |

Les coefficients (`COEF_ETAT`), la remise (`REMISE_ACHAT`) et le pas d'arrondi (`PAS_ARRONDI`)
se règlent en haut de `estimation_cartes.py`.

Colonnes du CSV : `carte`, `nom`, `extension`, `etat`, `quantite`, `image` (lien vers l'image de la carte),
`prix`, `prix_achat`, `total_achat`, `lien` (page Cardmarket), `erreur`.

## Utilisation dans une autre application

```python
from estimation_cartes import estimer
resultats, total_achat = estimer([{"carte": "PFL01", "etat": "NM"}])
```
