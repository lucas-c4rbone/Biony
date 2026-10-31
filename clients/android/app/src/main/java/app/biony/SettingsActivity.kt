package app.biony

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.text.InputType
import android.view.Gravity
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import java.util.Calendar

/** Endereço do servidor, atalho na notificação e testes das ações do celular (sem precisar do servidor). */
class SettingsActivity : Activity() {
    private lateinit var address: EditText
    private lateinit var notificationSwitch: Switch

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val pad = dp(20)
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad * 2)
        }

        column.addView(title("Servidor"))
        column.addView(note("O endereço HTTPS do Biony pelo Tailscale (o mesmo que você abre no navegador)."))
        address = EditText(this).apply {
            hint = "https://seu-servidor.tailnet.ts.net"
            inputType = InputType.TYPE_TEXT_VARIATION_URI
            setSingleLine()
            setText(Prefs.serverUrl(this@SettingsActivity).orEmpty())
        }
        column.addView(address)
        column.addView(button("Salvar e abrir") { save() })

        column.addView(title("Atalhos"))
        notificationSwitch = Switch(this).apply {
            text = "Atalho fixo na barra de notificações"
            textSize = 16f
            isChecked = Prefs.notificationShortcut(this@SettingsActivity) && NotificationShortcut.canPost(this@SettingsActivity)
            setOnCheckedChangeListener { _, checked -> if (isPressed) toggleNotification(checked) }
        }
        column.addView(notificationSwitch)
        column.addView(
            note(
                "Também dá para pressionar e segurar o ícone do app (\"Falar com o Biony\") e adicionar o " +
                    "ladrilho \"Falar com o Biony\" ao painel rápido (puxe a barra de cima e toque em editar).",
            ),
        )

        column.addView(title("Testes"))
        column.addView(note("Testam o celular sem passar pelo servidor."))
        column.addView(button("Timer de 10 segundos") { test("""[{"tipo":"timer","segundos":10}]""") })
        column.addView(button("Despertador daqui a 2 minutos") { testAlarm() })
        column.addView(button("Lanterna por 3 segundos") { testFlashlight() })

        column.addView(title("Para não ser fechado"))
        column.addView(
            note(
                "No POCO/Xiaomi: em \"Bateria\" escolha \"Sem restrições\", ative o \"Início automático\" e " +
                    "trave o app na tela de apps recentes (segure o card e toque no cadeado).",
            ),
        )
        column.addView(button("Abrir ajustes do app") {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
        })

        setContentView(ScrollView(this).apply { addView(column) })
    }

    private fun save() {
        val url = Prefs.normalizeUrl(address.text.toString())
        if (url == null) {
            toast("Use um endereço HTTPS, sem espaços (ex.: https://servidor.tailnet.ts.net).")
            return
        }
        Prefs.setServerUrl(this, url)
        startActivity(
            Intent(this, MainActivity::class.java)
                .putExtra("recarregar", true)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
        )
        finish()
    }

    private fun toggleNotification(enabled: Boolean) {
        if (enabled && !NotificationShortcut.canPost(this)) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 2)
            return
        }
        applyNotification(enabled)
    }

    private fun applyNotification(enabled: Boolean) {
        Prefs.setNotificationShortcut(this, enabled)
        if (enabled) NotificationShortcut.show(this) else NotificationShortcut.hide(this)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != 2) return
        val granted = grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED
        notificationSwitch.isChecked = granted
        if (granted) applyNotification(true) else toast("Sem permissão de notificação, o atalho não aparece.")
    }

    private fun test(json: String) = PhoneActions.runAll(this, json)

    private fun testAlarm() {
        val soon = Calendar.getInstance().apply { add(Calendar.MINUTE, 2) }
        test("""[{"tipo":"despertador","hora":${soon.get(Calendar.HOUR_OF_DAY)},"minuto":${soon.get(Calendar.MINUTE)},"mensagem":"Teste do Biony"}]""")
        toast("Apague esse despertador no app Relógio depois do teste.")
    }

    private fun testFlashlight() {
        test("""[{"tipo":"lanterna","ligar":true}]""")
        Handler(Looper.getMainLooper()).postDelayed({ test("""[{"tipo":"lanterna","ligar":false}]""") }, 3000)
    }

    private fun toast(text: String) = Toast.makeText(this, text, Toast.LENGTH_LONG).show()

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    private fun title(text: String) = TextView(this).apply {
        this.text = text
        textSize = 20f
        setTextColor(Color.parseColor("#4fd1e8"))
        setPadding(0, dp(24), 0, dp(6))
    }

    private fun note(text: String) = TextView(this).apply {
        this.text = text
        textSize = 14f
        setTextColor(Color.parseColor("#8a9ab0"))
        setPadding(0, 0, 0, dp(8))
    }

    private fun button(text: String, onClick: () -> Unit) = Button(this).apply {
        this.text = text
        isAllCaps = false
        gravity = Gravity.CENTER
        layoutParams = LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        setOnClickListener { onClick() }
    }
}
