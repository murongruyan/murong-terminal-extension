import groovy.json.JsonOutput
import groovy.json.JsonSlurper
import java.io.File
import java.util.Base64
import java.util.Properties
import java.nio.file.Paths
import java.security.MessageDigest
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
}

val localProperties = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) {
        file.inputStream().use(::load)
    }
}

val appVersionName = (findProperty("APP_VERSION_NAME") as String?)
    ?.takeIf { it.isNotBlank() }
    ?: "1.3"
val appVersionCode = (findProperty("APP_VERSION_CODE") as String?)
    ?.toIntOrNull()
    ?: 26071513
val bundledToolchainAbi = (findProperty("BUNDLED_TOOLCHAIN_ABI") as String?)
    ?.takeIf { it.isNotBlank() }
    ?: "arm64-v8a"
val bundledToolchainVersion = (findProperty("BUNDLED_TOOLCHAIN_VERSION") as String?)
    ?.takeIf { it.isNotBlank() }
    ?: "termux-curated-v2"
val bundledToolchainDownloadEnabled = ((findProperty("BUNDLED_TOOLCHAIN_ENABLE_DOWNLOAD") as String?)
    ?: System.getenv("BUNDLED_TOOLCHAIN_ENABLE_DOWNLOAD"))
    ?.toBooleanStrictOrNull()
    ?: false
val bundledToolchainDownloadTimeout = ((findProperty("BUNDLED_TOOLCHAIN_DOWNLOAD_TIMEOUT") as String?)
    ?: System.getenv("BUNDLED_TOOLCHAIN_DOWNLOAD_TIMEOUT"))
    ?.toIntOrNull()
    ?: 30
val bundledToolchainDownloadRetries = ((findProperty("BUNDLED_TOOLCHAIN_DOWNLOAD_RETRIES") as String?)
    ?: System.getenv("BUNDLED_TOOLCHAIN_DOWNLOAD_RETRIES"))
    ?.toIntOrNull()
    ?: 3

val generatedToolchainSourceDir = layout.buildDirectory.dir("generated/toolchain/source")
val generatedToolchainAssetsDir = layout.buildDirectory.dir("generated/assets/toolchain")
val generatedToolchainJniLibsDir = layout.buildDirectory.dir("generated/jnilibs/toolchain")
val bundledToolchainPrebuiltRoot = rootProject.layout.projectDirectory.dir("toolchain/prebuilt/$bundledToolchainAbi").asFile

fun computeBundledCommandInstallName(commandName: String): String {
    val encoded = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(commandName.toByteArray(Charsets.UTF_8))
    return "libmurong_ext_${encoded}.so"
}

data class BundledToolchainLink(
    val path: String,
    val target: String
)

data class BundledToolchainLayout(
    val symlinks: List<BundledToolchainLink> = emptyList(),
    val executables: Set<String> = emptySet()
)

val bundledToolchainRootPrefix = "data/data/com.termux/files/usr/"

fun readBundledToolchainLayout(sourceRoot: File): BundledToolchainLayout {
    val layoutFile = File(sourceRoot, "metadata/toolchain-layout.json")
    if (!layoutFile.exists()) return BundledToolchainLayout()
    val payload = JsonSlurper().parse(layoutFile) as? Map<*, *> ?: return BundledToolchainLayout()
    val symlinks = (payload["symlinks"] as? List<*>)
        ?.mapNotNull { raw ->
            val item = raw as? Map<*, *> ?: return@mapNotNull null
            val path = item["path"]?.toString()?.takeIf { it.isNotBlank() } ?: return@mapNotNull null
            val target = item["target"]?.toString()?.takeIf { it.isNotBlank() } ?: return@mapNotNull null
            BundledToolchainLink(path = path, target = target)
        }
        .orEmpty()
    val executables = (payload["executables"] as? List<*>)
        ?.mapNotNull { it?.toString()?.takeIf(String::isNotBlank) }
        ?.toSet()
        .orEmpty()
    return BundledToolchainLayout(symlinks = symlinks, executables = executables)
}

fun resolveBundledToolchainRelative(path: String, target: String): String {
    val normalizedTarget = target
        .replace('\\', '/')
        .removePrefix("/")
        .removePrefix(bundledToolchainRootPrefix)
    val parent = Paths.get(path).parent
    val resolved = (parent ?: Paths.get("")).resolve(normalizedTarget).normalize()
    return resolved.toString().replace('\\', '/')
}

fun resolveBundledToolchainTarget(
    path: String,
    symlinkTargets: Map<String, String>
): String {
    var current = resolveBundledToolchainRelative(path, symlinkTargets[path] ?: return path)
    val seen = linkedSetOf(path)
    while (true) {
        val nextTarget = symlinkTargets[current] ?: return current
        if (!seen.add(current)) return current
        current = resolveBundledToolchainRelative(current, nextTarget)
    }
}

fun hashBundledToolchainFile(file: File): String {
    val digest = MessageDigest.getInstance("SHA-256")
    file.inputStream().use { input ->
        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
        while (true) {
            val read = input.read(buffer)
            if (read <= 0) break
            digest.update(buffer, 0, read)
        }
    }
    return digest.digest().joinToString("") { "%02x".format(it) }
}

fun collectBundledToolchainDuplicateTargets(filesByRelative: Map<String, File>): Map<String, String> {
    val canonicalBySignature = linkedMapOf<String, String>()
    val duplicateTargets = linkedMapOf<String, String>()
    filesByRelative.toSortedMap().forEach { (relativePath, file) ->
        val signature = "${file.length()}:${hashBundledToolchainFile(file)}"
        val canonicalPath = canonicalBySignature.putIfAbsent(signature, relativePath)
        if (canonicalPath != null) {
            duplicateTargets[relativePath] = canonicalPath
        }
    }
    return duplicateTargets
}

fun buildBundledToolchainRelativeLink(path: String, targetPath: String): String {
    val parent = Paths.get(path).parent ?: Paths.get("")
    return parent.relativize(Paths.get(targetPath)).toString().replace('\\', '/')
}

fun isElfExecutable(file: File): Boolean {
    if (!file.isFile || file.length() < 4) return false
    return file.inputStream().use { input ->
        input.read() == 0x7f && input.read() == 'E'.code && input.read() == 'L'.code && input.read() == 'F'.code
    }
}

fun preparePlaceholderToolchain(sourceRoot: File) {
    sourceRoot.deleteRecursively()
    File(sourceRoot, "bin").mkdirs()
    File(sourceRoot, "lib").mkdirs()
    File(sourceRoot, "metadata").mkdirs()
    File(sourceRoot, "metadata/README.txt").writeText(
        "No bundled toolchain source is staged yet. Enable -PBUNDLED_TOOLCHAIN_ENABLE_DOWNLOAD=true " +
            "or let GitHub Actions populate this directory before packaging.",
        Charsets.UTF_8
    )
}

fun generateBundledToolchainAssets(
    sourceRoot: File,
    abi: String,
    version: String,
    outputRoot: File
) {
    val abiDir = File(outputRoot, "toolchain/$abi")
    val layout = readBundledToolchainLayout(sourceRoot)
    val allFiles = if (sourceRoot.exists()) {
        sourceRoot.walkTopDown().filter { it.isFile }.sortedBy { it.invariantSeparatorsPath }.toList()
    } else {
        emptyList()
    }
    val allFilesByRelative = allFiles.associateBy { it.relativeTo(sourceRoot).invariantSeparatorsPath }
    val duplicateTargets = collectBundledToolchainDuplicateTargets(allFilesByRelative)
    val symlinkTargets = layout.symlinks.associate { it.path to it.target }
    val commandMappings = linkedMapOf<String, String>()
    val deduplicatedLinks = linkedMapOf<String, String>()

    outputRoot.deleteRecursively()
    abiDir.mkdirs()

    allFilesByRelative.forEach { (relative, source) ->
        if (relative.startsWith("bin/") && isElfExecutable(source)) {
            val commandName = source.name
            val canonicalRelative = duplicateTargets[relative] ?: relative
            val canonicalCommandName = File(canonicalRelative).name
            commandMappings[commandName] = "native/${computeBundledCommandInstallName(canonicalCommandName)}"
            return@forEach
        }
        val canonicalRelative = duplicateTargets[relative]
        if (canonicalRelative != null) {
            deduplicatedLinks[relative] = buildBundledToolchainRelativeLink(relative, canonicalRelative)
            return@forEach
        }
        val target = File(abiDir, relative)
        target.parentFile?.mkdirs()
        source.copyTo(target, overwrite = true)
        target.setReadable(true, false)
        if (relative in layout.executables) {
            target.setExecutable(true, false)
        }
    }

    layout.symlinks
        .filter { it.path.startsWith("bin/") }
        .forEach { link ->
            val resolvedTarget = resolveBundledToolchainTarget(link.path, symlinkTargets)
            val targetFile = allFilesByRelative[resolvedTarget]
            val commandName = File(link.path).name
            if (targetFile != null && isElfExecutable(targetFile)) {
                commandMappings[commandName] = "native/${computeBundledCommandInstallName(File(resolvedTarget).name)}"
            } else {
                commandMappings[commandName] = resolvedTarget
            }
        }

    allFilesByRelative
        .filter { (relative, source) -> relative.startsWith("bin/") && !isElfExecutable(source) }
        .forEach { (relative, _) ->
            commandMappings[File(relative).name] = relative
        }

    val assetFiles = allFilesByRelative.keys
        .filterNot { it.startsWith("bin/") && isElfExecutable(allFilesByRelative.getValue(it)) }
        .filterNot { it in deduplicatedLinks.keys }
        .filterNot { it == "metadata/toolchain-layout.json" }
        .sorted()
    val manifestPayload = linkedMapOf<String, Any>(
        "version" to version,
        "abi" to abi,
        "files" to assetFiles.map { relativePath ->
            linkedMapOf(
                "asset" to relativePath,
                "path" to relativePath,
                "executable" to (relativePath in layout.executables)
            )
        },
        "links" to layout.symlinks
            .filterNot { it.path.startsWith("bin/") }
            .map { link ->
                linkedMapOf(
                    "path" to link.path,
                    "target" to link.target
                )
            } + deduplicatedLinks.entries.sortedBy { it.key }.map { (path, target) ->
                linkedMapOf(
                    "path" to path,
                    "target" to target
                )
            },
        "commands" to commandMappings
    )

    val manifestJson = JsonOutput.prettyPrint(JsonOutput.toJson(manifestPayload))
    File(abiDir, "manifest.json").writeText(manifestJson, Charsets.UTF_8)
}

fun generateBundledToolchainJniLibs(
    sourceRoot: File,
    abi: String,
    outputRoot: File
) {
    val abiDir = File(outputRoot, abi)
    val binDir = File(sourceRoot, "bin")
    val executableSources = if (binDir.exists()) {
        binDir.listFiles()?.filter { it.isFile && isElfExecutable(it) }?.sortedBy { it.name }.orEmpty()
    } else {
        emptyList()
    }
    val duplicateTargets = collectBundledToolchainDuplicateTargets(
        executableSources.associateBy { "bin/${it.name}" }
    )

    outputRoot.deleteRecursively()
    abiDir.mkdirs()

    executableSources.forEach { source ->
        val relativePath = "bin/${source.name}"
        if (duplicateTargets.containsKey(relativePath)) {
            return@forEach
        }
        val target = File(abiDir, computeBundledCommandInstallName(source.name))
        source.copyTo(target, overwrite = true)
        target.setExecutable(true, false)
        target.setReadable(true, false)
    }
}

fun runForegroundProcess(command: List<String>, workingDirectory: File, failureMessage: String) {
    val process = ProcessBuilder(command)
        .directory(workingDirectory)
        .redirectErrorStream(true)
        .start()
    val outputThread = Thread {
        process.inputStream.bufferedReader().useLines { lines ->
            lines.forEach(::println)
        }
    }
    outputThread.isDaemon = true
    outputThread.start()
    val exitCode = process.waitFor()
    outputThread.join()
    if (exitCode != 0) {
        throw GradleException("$failureMessage with exit code $exitCode.")
    }
}

val prepareBundledToolchainSource = tasks.register("prepareBundledToolchainSource") {
    val outputRoot = generatedToolchainSourceDir.get().asFile
    val prebuiltRoot = bundledToolchainPrebuiltRoot
    val scriptFile = rootProject.layout.projectDirectory.file("scripts/sync_toolchain.py").asFile
    val configFile = rootProject.layout.projectDirectory.file("toolchain/termux-curated-packages.json").asFile
    outputs.dir(outputRoot)
    inputs.property("abi", bundledToolchainAbi)
    inputs.property("version", bundledToolchainVersion)
    inputs.property("downloadEnabled", bundledToolchainDownloadEnabled)
    inputs.property("downloadTimeout", bundledToolchainDownloadTimeout)
    inputs.property("downloadRetries", bundledToolchainDownloadRetries)
    inputs.file(scriptFile)
    inputs.file(configFile)
    doLast {
        outputRoot.deleteRecursively()
        if (prebuiltRoot.exists()) {
            prebuiltRoot.copyRecursively(outputRoot, overwrite = true)
            return@doLast
        }
        if (!bundledToolchainDownloadEnabled) {
            preparePlaceholderToolchain(outputRoot)
            return@doLast
        }
        val pythonCommand = if (System.getProperty("os.name").startsWith("Windows", ignoreCase = true)) {
            listOf("py", "-3")
        } else {
            listOf("python3")
        }
        runForegroundProcess(
            pythonCommand +
                listOf(
                    scriptFile.absolutePath,
                    "--config", configFile.absolutePath,
                    "--output", outputRoot.absolutePath,
                    "--abi", bundledToolchainAbi,
                    "--timeout", bundledToolchainDownloadTimeout.toString(),
                    "--retries", bundledToolchainDownloadRetries.toString()
                ),
            rootProject.projectDir,
            "Toolchain sync script failed"
        )
    }
}

val refreshBundledToolchainPrebuilt = tasks.register("refreshBundledToolchainPrebuilt") {
    val outputRoot = bundledToolchainPrebuiltRoot
    val scriptFile = rootProject.layout.projectDirectory.file("scripts/sync_toolchain.py").asFile
    val configFile = rootProject.layout.projectDirectory.file("toolchain/termux-curated-packages.json").asFile
    inputs.property("abi", bundledToolchainAbi)
    inputs.property("downloadTimeout", bundledToolchainDownloadTimeout)
    inputs.property("downloadRetries", bundledToolchainDownloadRetries)
    inputs.file(scriptFile)
    inputs.file(configFile)
    outputs.dir(outputRoot)
    doLast {
        outputRoot.deleteRecursively()
        outputRoot.parentFile?.mkdirs()
        val pythonCommand = if (System.getProperty("os.name").startsWith("Windows", ignoreCase = true)) {
            listOf("py", "-3")
        } else {
            listOf("python3")
        }
        runForegroundProcess(
            pythonCommand +
                listOf(
                    scriptFile.absolutePath,
                    "--config", configFile.absolutePath,
                    "--output", outputRoot.absolutePath,
                    "--abi", bundledToolchainAbi,
                    "--timeout", bundledToolchainDownloadTimeout.toString(),
                    "--retries", bundledToolchainDownloadRetries.toString()
                ),
            rootProject.projectDir,
            "Toolchain prebuilt refresh failed"
        )
    }
}

val prepareBundledToolchainAssets = tasks.register("prepareBundledToolchainAssets") {
    val sourceRoot = generatedToolchainSourceDir.get().asFile
    val outputRoot = generatedToolchainAssetsDir.get().asFile
    dependsOn(prepareBundledToolchainSource)
    inputs.dir(sourceRoot)
    inputs.property("abi", bundledToolchainAbi)
    inputs.property("version", bundledToolchainVersion)
    outputs.dir(outputRoot)
    doLast {
        generateBundledToolchainAssets(
            sourceRoot = sourceRoot,
            abi = bundledToolchainAbi,
            version = bundledToolchainVersion,
            outputRoot = outputRoot
        )
    }
}

val prepareBundledToolchainJniLibs = tasks.register("prepareBundledToolchainJniLibs") {
    val sourceRoot = generatedToolchainSourceDir.get().asFile
    val outputRoot = generatedToolchainJniLibsDir.get().asFile
    dependsOn(prepareBundledToolchainSource)
    inputs.dir(sourceRoot)
    inputs.property("abi", bundledToolchainAbi)
    outputs.dir(outputRoot)
    doLast {
        generateBundledToolchainJniLibs(
            sourceRoot = sourceRoot,
            abi = bundledToolchainAbi,
            outputRoot = outputRoot
        )
    }
}

android {
    namespace = "cc.rl1.murong.terminalextension"
    compileSdk = 37

    defaultConfig {
        applicationId = "cc.rl1.murong.terminalextension"
        minSdk = 33
        targetSdk = 37
        versionCode = appVersionCode
        versionName = appVersionName

        buildConfigField("String", "APP_VERSION_NAME", "\"$appVersionName\"")
        buildConfigField("String", "BUNDLED_TOOLCHAIN_ABI", "\"$bundledToolchainAbi\"")
        buildConfigField("String", "BUNDLED_TOOLCHAIN_VERSION", "\"$bundledToolchainVersion\"")
    }

    signingConfigs {
        create("release") {
            var keystoreFile = rootProject.file("../murongagent/app/release.jks")
            val legacyKeystoreFile = rootProject.file("../murongagent/app/慕容调度.jks")
            val localBase64Keystore = rootProject.file("../murongagent/app/release.jks.b64")
            val keystoreBase64 = (findProperty("KEYSTORE_BASE64") as String?)
                ?: System.getenv("KEYSTORE_BASE64")
            if (!keystoreBase64.isNullOrBlank()) {
                val cleaned = keystoreBase64
                    .replace("-----BEGIN CERTIFICATE-----", "")
                    .replace("-----END CERTIFICATE-----", "")
                    .replace("\r", "")
                    .replace("\n", "")
                    .trim()
                if (cleaned.isNotEmpty()) {
                    keystoreFile.parentFile?.mkdirs()
                    keystoreFile.writeBytes(Base64.getDecoder().decode(cleaned))
                }
            } else if (!keystoreFile.exists() && legacyKeystoreFile.exists()) {
                keystoreFile = legacyKeystoreFile
            } else if (!keystoreFile.exists() && localBase64Keystore.exists()) {
                val cleaned = localBase64Keystore
                    .readText(Charsets.UTF_8)
                    .replace("-----BEGIN CERTIFICATE-----", "")
                    .replace("-----END CERTIFICATE-----", "")
                    .replace("\r", "")
                    .replace("\n", "")
                    .trim()
                if (cleaned.isNotEmpty()) {
                    keystoreFile.parentFile?.mkdirs()
                    keystoreFile.writeBytes(Base64.getDecoder().decode(cleaned))
                }
            }
            storeFile = keystoreFile
            storePassword =
                localProperties.getProperty("storePassword")
                    ?: (findProperty("STORE_PASSWORD") as String?)
                    ?: System.getenv("STORE_PASSWORD")
                    ?: ""
            keyAlias = "慕容调度"
            keyPassword =
                localProperties.getProperty("keyPassword")
                    ?: (findProperty("KEY_PASSWORD") as String?)
                    ?: System.getenv("KEY_PASSWORD")
                    ?: ""
            enableV1Signing = true
            enableV2Signing = true
            enableV3Signing = true
            enableV4Signing = true
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            signingConfig = signingConfigs.getByName("release")
        }
        debug {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
    }

    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }

    sourceSets.getByName("main").assets.directories.add(generatedToolchainAssetsDir.get().asFile.absolutePath)
    sourceSets.getByName("main").jniLibs.directories.add(generatedToolchainJniLibsDir.get().asFile.absolutePath)
}

tasks.matching { it.name.startsWith("merge") && it.name.endsWith("Assets") }.configureEach {
    dependsOn(prepareBundledToolchainAssets)
}

tasks.matching { it.name.startsWith("merge") && it.name.endsWith("NativeLibs") }.configureEach {
    dependsOn(prepareBundledToolchainJniLibs)
}

tasks.matching { it.name.startsWith("merge") && it.name.endsWith("JniLibFolders") }.configureEach {
    dependsOn(prepareBundledToolchainJniLibs)
}

tasks.matching {
    it.name == "generateReleaseLintVitalReportModel" ||
        it.name == "lintVitalAnalyzeRelease"
}.configureEach {
    dependsOn(prepareBundledToolchainAssets)
    dependsOn(prepareBundledToolchainJniLibs)
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(libs.core.ktx)
}
