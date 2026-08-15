"""
Tests des helpers extraits de transcribe_audio (stt_whisper).

La décomposition de la god-function rend la collecte de segments et le
post-traitement testables sans charger le modèle Faster-Whisper (~1.5 GB).
"""
from unittest.mock import MagicMock

from app.services.stt_whisper import _collect_segments, _postprocess_transcription


class _Seg:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text


def _fake_info(language="fr", prob=0.95):
    info = MagicMock()
    info.language = language
    info.language_probability = prob
    return info


class TestCollectSegments:
    def test_concatene_et_strip_les_segments(self):
        segs = [_Seg(0.0, 1.0, "  bonjour "), _Seg(1.0, 2.0, " le riz ")]
        all_segments, text = _collect_segments(iter(segs))
        assert text == "bonjour le riz"
        assert all_segments == [
            {"start": 0.0, "end": 1.0, "text": "bonjour"},
            {"start": 1.0, "end": 2.0, "text": "le riz"},
        ]

    def test_aucun_segment(self):
        all_segments, text = _collect_segments(iter([]))
        assert all_segments == []
        assert text == ""


class TestPostprocessTranscription:
    def test_texte_normal_construit_le_dict(self):
        info = _fake_info()
        segs = [{"start": 0.0, "end": 1.0, "text": "je cultive du riz"}]
        res = _postprocess_transcription("je cultive du riz", info, segs)
        assert res is not None
        assert res["language"] == "fr"
        assert res["language_probability"] == 0.95
        assert res["segments"] is segs
        assert "text" in res and res["text"]
        assert res["likely_dioula_input"] in (True, False)

    def test_hallucination_retourne_none(self):
        # Une chaîne vide est jugée hallucination par is_likely_hallucination.
        info = _fake_info()
        assert _postprocess_transcription("", info, []) is None
