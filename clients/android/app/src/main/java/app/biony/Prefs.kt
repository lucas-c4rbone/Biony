package app.biony

import android.content.Context

/** Configurações do app (só guardam o endereço do servidor e o atalho; senha e token ficam na PWA). */
object Prefs {
    private const val FILE = "biony"
    private const val KEY_URL = "url"
    private const val KEY_NOTIFICATION = "atalho_notificacao"

    private fun prefs(context: Context) = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    fun serverUrl(context: Context): String? = prefs(context).getString(KEY_URL, null)?.takeIf { it.isNotBlank() }

    fun setServerUrl(context: Context, url: String) = prefs(context).edit().putString(KEY_URL, url).apply()

    fun notificationShortcut(context: Context): Boolean = prefs(context).getBoolean(KEY_NOTIFICATION, false)

    fun setNotificationShortcut(context: Context, enabled: Boolean) =
        prefs(context).edit().putBoolean(KEY_NOTIFICATION, enabled).apply()

    /**
     * Aceita "meuservidor.ts.net" ou "https://meuservidor.ts.net/" e devolve "https://meuservidor.ts.net/".
     * Só HTTPS: o microfone do WebView não funciona sem ele, e o token da conversa não deve viajar aberto.
     */
    fun normalizeUrl(input: String): String? {
        var text = input.trim()
        if (text.isEmpty() || text.contains(' ')) return null
        // HTTP só em testes (debug) e só para localhost, via "adb reverse".
        if (BuildConfig.DEBUG && text.startsWith("http://localhost")) return if (text.endsWith("/")) text else "$text/"
        if (text.startsWith("http://")) return null
        if (!text.startsWith("https://")) text = "https://$text"
        return if (text.endsWith("/")) text else "$text/"
    }
}
