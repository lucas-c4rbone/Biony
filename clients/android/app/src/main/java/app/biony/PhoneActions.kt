package app.biony

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.provider.AlarmClock
import android.util.Log
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import java.util.Calendar

/**
 * Executa as ações que o servidor devolve em `acoes` (ver protocol/PROTOCOL.md).
 * Só existe uma lista fixa de ações; qualquer outra coisa é ignorada.
 */
object PhoneActions {
    private const val TAG = "BionyAcoes"
    private val DAYS = mapOf(
        "dom" to Calendar.SUNDAY, "seg" to Calendar.MONDAY, "ter" to Calendar.TUESDAY, "qua" to Calendar.WEDNESDAY,
        "qui" to Calendar.THURSDAY, "sex" to Calendar.FRIDAY, "sab" to Calendar.SATURDAY,
    )

    fun runAll(context: Context, json: String) {
        val actions = try {
            JSONArray(json)
        } catch (error: Exception) {
            Log.w(TAG, "JSON de ações inválido", error)
            return
        }
        for (index in 0 until actions.length()) {
            val action = actions.optJSONObject(index) ?: continue
            try {
                run(context, action)
            } catch (error: Exception) {
                Log.w(TAG, "Falhou: ${action.optString("tipo")}", error)
                toast(context, "Não consegui (${action.optString("tipo")}): ${error.message ?: error.javaClass.simpleName}")
            }
        }
    }

    private fun run(context: Context, action: JSONObject) {
        when (action.optString("tipo")) {
            "despertador" -> alarm(context, action)
            "timer" -> timer(context, action)
            "lanterna" -> flashlight(context, action.optBoolean("ligar"))
            "abrir_app" -> openApp(context, action.optString("app"))
            else -> Log.w(TAG, "Ação desconhecida ignorada: ${action.optString("tipo")}")
        }
    }

    private fun alarm(context: Context, action: JSONObject) {
        val hour = action.getInt("hora")
        val minute = action.optInt("minuto", 0)
        val intent = Intent(AlarmClock.ACTION_SET_ALARM)
            .putExtra(AlarmClock.EXTRA_HOUR, hour)
            .putExtra(AlarmClock.EXTRA_MINUTES, minute)
            .putExtra(AlarmClock.EXTRA_SKIP_UI, true)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        action.optString("mensagem").takeIf { it.isNotBlank() }?.let { intent.putExtra(AlarmClock.EXTRA_MESSAGE, it) }
        val days = action.optJSONArray("dias")
        if (days != null && days.length() > 0) {
            val calendarDays = ArrayList<Int>()
            for (i in 0 until days.length()) DAYS[days.optString(i)]?.let { calendarDays.add(it) }
            intent.putExtra(AlarmClock.EXTRA_DAYS, calendarDays)
        }
        context.startActivity(intent)
        toast(context, "⏰ Despertador às %02d:%02d enviado ao Relógio".format(hour, minute))
    }

    private fun timer(context: Context, action: JSONObject) {
        val seconds = action.getInt("segundos")
        val intent = Intent(AlarmClock.ACTION_SET_TIMER)
            .putExtra(AlarmClock.EXTRA_LENGTH, seconds)
            .putExtra(AlarmClock.EXTRA_SKIP_UI, true)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        action.optString("mensagem").takeIf { it.isNotBlank() }?.let { intent.putExtra(AlarmClock.EXTRA_MESSAGE, it) }
        context.startActivity(intent)
        toast(context, "⏳ Timer de ${formatSeconds(seconds)} enviado ao Relógio")
    }

    private fun flashlight(context: Context, on: Boolean) {
        val manager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val id = manager.cameraIdList.firstOrNull { camera ->
            val info = manager.getCameraCharacteristics(camera)
            info.get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true &&
                info.get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK
        } ?: throw IllegalStateException("sem lanterna")
        manager.setTorchMode(id, on)
        toast(context, if (on) "🔦 Lanterna ligada" else "Lanterna desligada")
    }

    private fun openApp(context: Context, name: String) {
        if (AppMatcher.normalize(name).isEmpty()) return
        val pm = context.packageManager
        val launcher = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val found = pm.queryIntentActivities(launcher, PackageManager.MATCH_ALL).associateBy {
            AppMatcher.App(it.loadLabel(pm).toString(), it.activityInfo.packageName)
        }
        val app = AppMatcher.pick(name, found.keys.toList())
        if (app == null) {
            toast(context, "Não achei o app \"$name\"")
            return
        }
        val info = found.getValue(app).activityInfo
        context.startActivity(
            Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
                .setClassName(info.packageName, info.name)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        )
    }

    private fun formatSeconds(seconds: Int): String = when {
        seconds % 3600 == 0 -> "${seconds / 3600} h"
        seconds % 60 == 0 -> "${seconds / 60} min"
        else -> "$seconds s"
    }

    private fun toast(context: Context, text: String) = Toast.makeText(context, text, Toast.LENGTH_SHORT).show()
}
