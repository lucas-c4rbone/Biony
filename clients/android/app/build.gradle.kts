plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "app.biony"
    compileSdk = 35

    defaultConfig {
        applicationId = "app.biony.assistente"
        minSdk = 26
        // 34 (e não 35): o 35 força tela de ponta a ponta e a PWA não trata as margens do sistema dentro do app.
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            // Uso próprio: assina com a chave de debug (sem Play Store), mas sem as exceções de teste.
            signingConfig = signingConfigs.getByName("debug")
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}
