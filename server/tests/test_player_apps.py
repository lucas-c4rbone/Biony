from __future__ import annotations

from biony.player_apps import parse_packages, suggest

RESPONSE = """package:com.amazon.tv.settings.v2
package:com.netflix.ninja
package:com.amazon.firetv.youtube
package:com.example.meuapp

package:com.netflix.ninja
"""


def test_parse_packages_ignores_noise_and_duplicates():
    assert parse_packages(RESPONSE) == [
        "com.amazon.firetv.youtube", "com.amazon.tv.settings.v2", "com.example.meuapp", "com.netflix.ninja",
    ]
    assert parse_packages("") == [] and parse_packages("Error: device offline") == []


def test_suggest_names_known_apps_and_lists_the_rest():
    everything = parse_packages(RESPONSE)
    user_apps = ["com.example.meuapp", "com.netflix.ninja"]
    known, others = suggest(everything, user_apps)
    assert known == {"Netflix": "com.netflix.ninja", "YouTube": "com.amazon.firetv.youtube"}
    assert others == ["com.example.meuapp"]  # o Netflix já tem nome; o app de sistema não entra
