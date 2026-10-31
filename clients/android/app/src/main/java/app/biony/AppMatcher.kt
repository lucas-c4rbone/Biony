package app.biony

import java.text.Normalizer

/**
 * Descobre qual app instalado o Lucas quis dizer ("youtube music" → o app que se chama "YT Music").
 * Compara o nome que aparece no celular e também o nome interno do pacote (com.google...youtube.music),
 * e entende alguns apelidos ("zap", "yt"). Sem dependência do Android, para poder ser testado no PC.
 */
object AppMatcher {
    data class App(val label: String, val packageName: String)

    // Apelidos que valem para o que ele fala e para o nome do app (os dois lados passam por aqui).
    private val ALIASES = mapOf(
        "yt" to "youtube",
        "zap" to "whatsapp",
        "zapzap" to "whatsapp",
        "insta" to "instagram",
        "face" to "facebook",
        "musica" to "music",
    )

    fun normalize(text: String): String =
        Normalizer.normalize(text, Normalizer.Form.NFD)
            .replace(Regex("\\p{Mn}+"), "")
            .lowercase()
            .replace(Regex("[^a-z0-9]+"), " ")
            .trim()

    private fun tokens(text: String): List<String> =
        normalize(text).split(" ").filter { it.isNotEmpty() }.map { ALIASES[it] ?: it }

    /** O app que melhor combina com `query`, ou null se nenhum combinar. */
    fun pick(query: String, apps: List<App>): App? {
        val wanted = tokens(query)
        if (wanted.isEmpty()) return null
        return apps
            .map { it to score(wanted, it) }
            .filter { it.second > 0 }
            // Em empate, o de nome mais curto (o "YouTube" puro ganha de "YouTube Kids" para "youtube").
            .sortedWith(compareByDescending<Pair<App, Int>> { it.second }.thenBy { it.first.label.length })
            .firstOrNull()?.first
    }

    private fun score(wanted: List<String>, app: App): Int {
        val label = tokens(app.label)
        // Pacote em pedaços ("com.google.android.apps.youtube.music" → youtube, music, ...).
        val pkg = app.packageName.split('.').flatMap { tokens(it) }
        fun prefixed(pool: List<String>) = wanted.all { w -> pool.any { it.startsWith(w) } }
        return when {
            label == wanted -> 100
            label.containsAll(wanted) -> 80 - (label.size - wanted.size)
            prefixed(label) -> 60 - (label.size - wanted.size).coerceAtLeast(0)
            prefixed(label + pkg) -> 40
            else -> 0
        }
    }
}
