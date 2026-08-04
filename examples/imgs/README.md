# Lokalny korpus zdjęć M5

Umieść w tym katalogu oryginalne zdjęcia wskazane przez
`ai_docs/quality/m5-corpus-manifest.json`.

Pliki obrazów są celowo ignorowane przez Git. Manifest przechowuje wyłącznie
ścieżki względne, wymiary, rozmiary, SHA-256 i metadane korpusu. Walidator nie
modyfikuje obrazów:

```powershell
.venv\Scripts\python.exe scripts\validate_m5_corpus.py
```

Pełna bramka G5.1 wymaga dodatkowo kompletnych golden annotations:

```powershell
.venv\Scripts\python.exe scripts\validate_m5_corpus.py --require-complete
```
