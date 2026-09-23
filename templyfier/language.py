"""Small reviewed French/English vocabulary for analysis only, not translation.

Never use this representation as a source ID, clean label or memory anchor.
Unknown wording stays unknown; semantic equivalence is not inferred across languages.
"""
import re
import unicodedata

PHRASES={
    'opinion globale sur le produit':'overall product opinion',
    'opinion globale du produit':'overall product opinion',
    'appreciation globale du produit':'overall product liking',
    'avis global sur le produit':'overall product opinion',
    'opinion globale sur le parfum':'overall fragrance opinion',
    'opinion globale du parfum':'overall fragrance opinion',
    'appreciation globale du parfum':'overall fragrance liking',
    'intention d achat':'purchase intent','intentions d achat':'purchase intent',
    'satisfaction globale':'overall satisfaction',
    'comparaison avec le produit habituel':'comparison to current',
    'compare au produit habituel':'compared to current',
    'comparaison au produit actuel':'comparison to current',
    'comparaison avec le produit actuel':'comparison to current',
    'produit prefere':'preferred product','produit favori':'preferred product',
    'attributs olfactifs':'olfactive attributes','caracteristiques du parfum':'fragrance characteristics',
    'benefices du produit':'product benefits','benefices du parfum':'fragrance benefits',
    'efficacite de nettoyage':'cleaning efficacy','performance de nettoyage':'cleaning performance',
    'elimination des taches':'stain removal','douceur globale':'overall softness',
    'fraicheur longue duree':'long lasting freshness','tenue du parfum':'long lasting fragrance',
    'quantite utilisee':'quantity used','temperature de lavage':'wash temp',
    'charge de linge':'wash load','methode de sechage':'dry method',
    'ouverture du flacon':'opening the bottle','ouverture de la bouteille':'opening the bottle',
    'machine a laver':'washing machine','au sechage':'while drying',
    'au porter':'when wearing','dans l armoire':'wardrobe',
    'trop faible':'too weak','trop fort':'too strong','trop forte':'too strong',
    'juste comme il faut':'just about right','ni trop faible ni trop fort':'just about right',
    'selectionner toutes':'select all','selectionnez toutes':'select all',
    'differentiel semantique':'semantic differential',
    'feminin':'feminine','masculin':'masculine','traditionnel':'traditional','moderne':'modern',
    'naturel':'natural','artificiel':'artificial','chaud':'warm','froid':'cool',
    'intensite':'intensity','douceur':'softness','fraicheur':'freshness','couleur':'color',
    'couleurs':'colors','emotions':'emotions','parfum':'fragrance','odeur':'smell',
    'attentes':'expectation','attente':'expectation','blancheur':'whiteness',
}

def analysis_normal(value):
    value=str(value).replace('’',' ').replace("'",' ')
    value=unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().casefold()
    value=re.sub(r'\s+',' ',value.replace('_',' ').replace('-',' ')).strip()
    # One pass: replacement text is never translated a second time.
    pattern=r'\b(?:'+'|'.join(re.escape(k) for k in sorted(PHRASES,key=len,reverse=True))+r')\b'
    return re.sub(pattern,lambda match:PHRASES[match[0]],value)

def french_box_key(normalized):
    match=re.fullmatch(r'(?:(1|2|3|une?|deux|trois) )?(?:boites?|cases?) (superieures?|inferieures?)',normalized)
    if not match:return None
    count={'un':'1','une':'1','deux':'2','trois':'3'}.get(match[1],match[1] or '1')
    return ('top_' if match[2].startswith('superieur') else 'bottom_')+count
