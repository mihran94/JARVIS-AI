import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}

android {
    namespace = "com.jarvisblue.mobile"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.jarvisblue.mobile"
        minSdk = 31
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables.useSupportLibrary = true
    }

    signingConfigs {
        create("release") {
            val keystorePropsFile = rootProject.file("keystore/keystore.properties")
            val keystoreProps = Properties().apply {
                if (keystorePropsFile.exists()) keystorePropsFile.inputStream().use { load(it) }
            }
            // The store path must never be empty here: rootProject.file("")
            // throws during configuration, and that would break the debug build
            // as well, because the whole project is configured before any task
            // runs. The keystore stays outside the repository, so this file is
            // simply absent on a fresh checkout.
            val storeFilePath = keystoreProps.getProperty("storeFile", "").trim()
            if (storeFilePath.isNotEmpty()) {
                val storePath = rootProject.file(storeFilePath)
                if (storePath.exists()) {
                    storeFile = storePath
                    storePassword = keystoreProps.getProperty("storePassword")
                    keyAlias = keystoreProps.getProperty("keyAlias")
                    keyPassword = keystoreProps.getProperty("keyPassword")
                }
            }
            // Sign with every scheme so the APK installs on sideloaders that
            // only understand v1 (older package installers) and on platforms
            // that prefer v3 (key rotation, stronger attestation).
            enableV1Signing = true
            enableV2Signing = true
            enableV3Signing = true
            enableV4Signing = false
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
            isMinifyEnabled = false
            isShrinkResources = false
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
        isCoreLibraryDesugaringEnabled = false
    }
    kotlinOptions {
        jvmTarget = "17"
        freeCompilerArgs += listOf("-opt-in=kotlin.RequiresOptIn")
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging {
        resources.excludes += setOf(
            "/META-INF/{AL2.0,LGPL2.1}",
            "/META-INF/DEPENDENCIES",
            "/META-INF/LICENSE*",
            "/META-INF/NOTICE*",
            "META-INF/*.kotlin_module",
        )
    }
    lint {
        abortOnError = false
        checkReleaseBuilds = false
        warningsAsErrors = false
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

// A release build must never be produced without a keystore. It would be
// distributed unsigned, or worse, signed with a key that is known to be
// exposed. The check runs only when a release task is actually requested, so
// the debug build is never affected.
gradle.taskGraph.whenReady {
    val wantsRelease = allTasks.any { it.path.startsWith(":app:") && it.path.contains("Release") }
    val releaseSigning = android.signingConfigs.getByName("release")
    if (wantsRelease && releaseSigning.storeFile == null) {
        throw GradleException(
            "No release keystore is configured. Create keystore/keystore.properties with " +
                "storeFile, storePassword, keyAlias and keyPassword, or build the debug " +
                "variant instead. See docs/ANDROID_SIGNING_KEY_ROTATION.md."
        )
    }
}

// The remote-only privacy guard checks that the Android launcher no longer
// exposes standalone assistant, microphone, boot or background tools.
// It runs before compiling the APK. It needs a Python interpreter; when there is none
// the build says so and carries on.
val checkSensitiveServices by tasks.registering(Exec::class) {
    group = "verification"
    description = "Fails the build if the Android remote exposes standalone AI/capture permissions"
    val script = rootProject.file("scripts/check_sensitive_services.py")
    val interpreter = listOf("python3", "python").firstOrNull { name ->
        providers.exec {
            commandLine(name, "--version")
            isIgnoreExitValue = true
        }.result.get().exitValue == 0
    }
    if (interpreter != null) {
        commandLine(interpreter, script.absolutePath)
    } else {
        logger.lifecycle("No Python interpreter was found, so the sensitive service guard did not run.")
        onlyIf { false }
    }
}

tasks.named("preBuild") { dependsOn(checkSensitiveServices) }

dependencies {
    implementation(project(":core:model"))
    implementation(project(":core:common"))
    implementation(project(":core:security"))
    implementation(project(":core:database"))
    implementation(project(":core:ai"))
    implementation(project(":core:tools"))
    implementation(project(":core:voice"))
    implementation(project(":core:windows"))
    implementation(project(":core:ui"))

    implementation(project(":feature:chat"))
    implementation(project(":feature:assistant"))
    implementation(project(":feature:studio"))
    implementation(project(":feature:command"))

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.process)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.androidx.work.runtime.ktx)
    implementation(libs.androidx.biometric)
    implementation(libs.androidx.fragment.ktx)

    implementation(libs.hilt.android)
    implementation(libs.androidx.hilt.work)
    ksp(libs.androidx.hilt.compiler)
    implementation(libs.androidx.hilt.work)
    ksp(libs.androidx.hilt.compiler)
    ksp(libs.hilt.compiler)
    implementation(libs.hilt.navigation.compose)

    implementation(libs.okhttp)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.foundation)
    implementation(libs.compose.animation)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons.extended)
    implementation(libs.compose.ui.tooling.preview)
    debugImplementation(libs.compose.ui.tooling)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.mockk)
    testImplementation(libs.turbine)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.androidx.test.espresso.core)
}
