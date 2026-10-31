package app.biony

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.webkit.JavascriptInterface
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient

/**
 * O Biony no celular: a própria PWA do servidor dentro de um WebView, mais o que a PWA sozinha não faz
 * (executar ações no celular, abrir já ouvindo pelo atalho, painel rápido e notificação).
 */
class MainActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var baseUrl: String
    private var serverHost = ""

    // Só páginas do servidor configurado podem usar a ponte (atualizado na UI thread, lido na thread da ponte).
    @Volatile private var trusted = false
    private var pendingMic: PermissionRequest? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val url = Prefs.serverUrl(this)
        if (url == null) {
            startActivity(Intent(this, SettingsActivity::class.java))
            finish()
            return
        }
        baseUrl = url
        serverHost = Uri.parse(url).host.orEmpty()

        web = WebView(this)
        setContentView(web)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true // a PWA guarda o login (token) aqui
            mediaPlaybackRequiresUserGesture = false // a resposta falada toca sozinha
            allowFileAccess = false
            allowContentAccess = false
        }
        web.addJavascriptInterface(Bridge(), "BionyApp")
        web.webViewClient = Client()
        web.webChromeClient = Chrome()
        web.loadUrl(startUrl(intent))
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent.getBooleanExtra("recarregar", false)) {
            // Voltou das configurações: o endereço pode ter mudado.
            val saved = Prefs.serverUrl(this) ?: return
            baseUrl = saved
            serverHost = Uri.parse(saved).host.orEmpty()
            web.loadUrl(startUrl(intent))
        } else if (intent.getBooleanExtra("ouvir", false)) {
            if (trusted) web.evaluateJavascript("window.bionyOuvir && window.bionyOuvir()", null)
            else web.loadUrl(startUrl(intent))
        }
    }

    private fun startUrl(intent: Intent): String =
        if (intent.getBooleanExtra("ouvir", false)) "$baseUrl?ouvir=1" else baseUrl

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (this::web.isInitialized && web.canGoBack()) web.goBack() else @Suppress("DEPRECATION") super.onBackPressed()
    }

    override fun onResume() {
        super.onResume()
        if (this::web.isInitialized) web.onResume()
    }

    override fun onPause() {
        if (this::web.isInitialized) web.onPause()
        super.onPause()
    }

    override fun onDestroy() {
        if (this::web.isInitialized) web.destroy()
        super.onDestroy()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        val request = pendingMic ?: return
        pendingMic = null
        if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
        } else {
            request.deny()
        }
    }

    private fun sameServer(url: String?): Boolean {
        val uri = Uri.parse(url ?: return false)
        val secure = uri.scheme == "https" || (BuildConfig.DEBUG && uri.scheme == "http" && uri.host == "localhost")
        return secure && uri.host == serverHost
    }

    private inner class Bridge {
        /** `acoes` do servidor (JSON). Só aceita de páginas do servidor configurado. */
        @JavascriptInterface
        fun executar(json: String) {
            if (!trusted) return
            runOnUiThread { PhoneActions.runAll(this@MainActivity, json) }
        }

        /** Também vale na tela de erro; abrir a configuração do próprio app não expõe nada. */
        @JavascriptInterface
        fun abrirConfiguracoes() {
            runOnUiThread { startActivity(Intent(this@MainActivity, SettingsActivity::class.java)) }
        }

        /** Botão "Tentar de novo" da tela de erro. */
        @JavascriptInterface
        fun recarregar() {
            runOnUiThread { web.loadUrl(startUrl(intent)) }
        }
    }

    private inner class Client : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            if (sameServer(request.url.toString())) return false
            // Qualquer outro endereço abre no navegador, nunca dentro do app (que tem a ponte).
            if (request.url.scheme == "https" || request.url.scheme == "http") {
                startActivity(Intent(Intent.ACTION_VIEW, request.url))
            }
            return true
        }

        override fun onPageStarted(view: WebView, url: String?, favicon: android.graphics.Bitmap?) {
            trusted = sameServer(url)
        }

        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
            if (!request.isForMainFrame) return
            trusted = false
            view.loadDataWithBaseURL(null, ERROR_PAGE, "text/html", "utf-8", null)
        }
    }

    private inner class Chrome : WebChromeClient() {
        override fun onPermissionRequest(request: PermissionRequest) {
            runOnUiThread {
                val onlyMic = request.resources.all { it == PermissionRequest.RESOURCE_AUDIO_CAPTURE }
                if (!trusted || !sameServer(request.origin.toString()) || !onlyMic) {
                    request.deny()
                } else if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                    request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
                } else {
                    pendingMic = request
                    requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1)
                }
            }
        }

        override fun onPermissionRequestCanceled(request: PermissionRequest) {
            if (pendingMic == request) pendingMic = null
        }
    }

    private companion object {
        const val ERROR_PAGE = """<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<body style="background:#0b1018;color:#e6edf6;font:16px system-ui;display:grid;place-content:center;
justify-items:center;gap:14px;height:100vh;margin:0;padding:24px;text-align:center">
<div style="font-size:48px">🔌</div>
<strong>Não consegui falar com o servidor</strong>
<span style="color:#8a9ab0">Confira se o Tailscale está ligado no celular e se o endereço está certo.</span>
<button onclick="BionyApp.recarregar()" style="padding:12px 20px;border:0;border-radius:12px;background:#4fd1e8;
color:#062027;font:600 16px system-ui">Tentar de novo</button>
<button onclick="BionyApp.abrirConfiguracoes()" style="padding:10px 18px;border:1px solid #1f2a3a;border-radius:12px;
background:transparent;color:#e6edf6;font:16px system-ui">Configurações</button>
</body>"""
    }
}
