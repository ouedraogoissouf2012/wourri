"""Diagnostic API sherpa-onnx 1.12.27"""
import sherpa_onnx

print(f"Version: {sherpa_onnx.__version__}")
print(f"\nType OfflineRecognizer: {sherpa_onnx.OfflineRecognizer}")
print(f"Module: {sherpa_onnx.OfflineRecognizer.__module__}")

# Verifier si c'est la meme classe que le binding C++
try:
    from sherpa_onnx.lib._sherpa_onnx import OfflineRecognizer as CppClass
    print(f"Meme que C++: {sherpa_onnx.OfflineRecognizer is CppClass}")
except Exception as e:
    print(f"Import C++: {e}")

# Afficher la signature
print("\nHelp OfflineRecognizer:")
help(sherpa_onnx.OfflineRecognizer)

# Lister les attributs du module
print("\nFonctions du module sherpa_onnx:")
for name in sorted(dir(sherpa_onnx)):
    if not name.startswith('_') and ('recogni' in name.lower() or 'offline' in name.lower()):
        obj = getattr(sherpa_onnx, name)
        print(f"  {name}: {type(obj).__name__}")
