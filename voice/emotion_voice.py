"""
Empathetic spoken responses when vision reports negative affect.
Supports EN, HI, MR, JA.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from voice.tts_output import TTSOutput

EMPATHY = {
    "en": "I sense you might be feeling down. I'm here with you. Would you like to talk or take a short break?",
    "hi": "मुझे लगता है आप उदास महसूस कर रहे हैं। मैं यहाँ हूँ। क्या आप बात करना चाहेंगे?",
    "mr": "तुम्ही निराश असल्यासारखं वाटतंय. मी येथे आहे. थोडं बोलायला हवं का?",
    "ja": "元気がないように見えます。話を聞きますよ。少し休みますか？",
}


def speak_empathetic(tts: Optional["TTSOutput"], language: str = "en") -> None:
    if tts is None:
        return
    msg = EMPATHY.get(language, EMPATHY["en"])
    tts.speak(msg, block=False)
