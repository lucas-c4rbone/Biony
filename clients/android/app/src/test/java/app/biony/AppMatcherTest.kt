package app.biony

import app.biony.AppMatcher.App
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class AppMatcherTest {
    // Parecido com o celular do Lucas: o app de música aparece como "YT Music".
    private val apps = listOf(
        App("YouTube", "com.google.android.youtube"),
        App("YT Music", "com.google.android.apps.youtube.music"),
        App("YouTube Kids", "com.google.android.apps.youtube.kids"),
        App("WhatsApp", "com.whatsapp"),
        App("WhatsApp Business", "com.whatsapp.w4b"),
        App("Instagram", "com.instagram.android"),
        App("Relógio", "com.google.android.deskclock"),
        App("Câmera", "com.android.camera"),
        App("Configurações", "com.android.settings"),
        App("Play Store", "com.android.vending"),
    )

    private fun pick(query: String) = AppMatcher.pick(query, apps)?.label

    @Test fun `youtube music acha o YT Music pelo nome do pacote e pelo apelido`() =
        assertEquals("YT Music", pick("YouTube Music"))

    @Test fun `youtube puro continua sendo o YouTube`() = assertEquals("YouTube", pick("youtube"))

    @Test fun `yt music e musica do youtube`() {
        assertEquals("YT Music", pick("yt music"))
        assertEquals("YT Music", pick("youtube música"))
    }

    @Test fun `nome exato ignora acento e maiusculas`() {
        assertEquals("Relógio", pick("relogio"))
        assertEquals("Câmera", pick("CAMERA"))
        assertEquals("Configurações", pick("configuracoes"))
    }

    @Test fun `apelidos`() {
        assertEquals("WhatsApp", pick("zap"))
        assertEquals("Instagram", pick("insta"))
    }

    @Test fun `comeco do nome basta`() = assertEquals("WhatsApp", pick("whats"))

    @Test fun `whatsapp puro vence o business`() = assertEquals("WhatsApp", pick("whatsapp"))

    @Test fun `play store com espaco`() = assertEquals("Play Store", pick("play store"))

    @Test fun `app que nao existe`() {
        assertNull(pick("netflix"))
        assertNull(pick("   "))
    }

    @Test fun `palavra solta nao pega app errado`() = assertNull(pick("music kids store"))
}
