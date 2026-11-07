package com.jarvisblue.core.tools

import com.jarvisblue.core.model.BridgeJob
import com.jarvisblue.core.model.BridgeRequest
import com.jarvisblue.core.model.MemoryKind
import com.jarvisblue.core.model.PcStatus
import com.jarvisblue.core.model.RiskLevel
import com.jarvisblue.core.model.ToolCategory
import com.jarvisblue.core.model.ToolParameter
import com.jarvisblue.core.model.ToolSpec
import com.jarvisblue.core.model.ParamType
import com.jarvisblue.core.model.Permission
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** A notification captured from the system's notification listener. */
data class NotificationSnapshot(
    val packageName: String,
    val appLabel: String,
    val title: String,
    val body: String,
    val postedAtEpochMs: Long,
    val ongoing: Boolean = false,
)

/**
 * App-level services that core:tools needs but cannot implement itself
 * (notification reading, screen capture, reminders and the Windows bridge).
 *
 * The app module provides the concrete implementation; the tools stay testable
 * because everything above this interface is pure Kotlin.
 */
interface AssistantServices {
    suspend fun recentNotifications(limit: Int = 20): List<NotificationSnapshot>
    suspend fun visibleScreenText(): String?
    suspend fun scheduleReminder(title: String, triggerAtEpochMs: Long): String
    suspend fun cancelReminder(taskId: String): Boolean
    suspend fun remoteStatus(): PcStatus
    suspend fun remoteJobs(): List<BridgeJob>
    suspend fun submitRemoteJob(request: BridgeRequest): BridgeJob
    suspend fun cancelRemoteJob(jobId: String): Boolean
}

/**
 * Registers every tool JARVIS BLUE can perform.
 *
 * The registry is the app's whole capability surface: if a capability is not
 * registered here, the model cannot request it, and the executor will reject
 * the call as an unknown tool.
 */
class JarvisToolRegistrar(
    private val registry: ToolRegistry,
    private val device: DeviceControlEngine,
    private val files: FileTools,
    private val network: NetworkDiagnostics,
    private val scanner: SecurityScanner,
    private val quality: CodeQualityChecker,
    private val quantum: QuantumSimulator,
    private val services: AssistantServices,
    val workspaceRoot: java.io.File,
) {

    fun registerAll() {
        registerDeviceTools()
        registerFileTools()
        registerSecurityTools()
        registerDevelopmentTools()
        registerQuantumTools()
        registerRemoteTools()
    }

    // ------------------------------------------------------------------ device

    private fun registerDeviceTools() {
        registry.register(
            ToolSpec(
                name = "open_app",
                displayName = "Open an app",
                description = "Launch an installed application by name.",
                category = ToolCategory.DEVICE,
                parameters = listOf(
                    ToolParameter("appName", ParamType.STRING, "Name of the app to launch", required = true),
                ),
                riskLevel = RiskLevel.LOW,
                requiredPermissions = setOf(Permission.PACKAGE_QUERY),
            ),
        ) { _, args ->
            val name = args.string("appName")
            val match = device.findApp(name)
                ?: throw IllegalArgumentException("No installed app matched '$name'")
            val message = device.launchApp(match.first)
            ToolOutput(message, mapOf("package" to match.first, "label" to match.second))
        }

        registry.register(
            ToolSpec(
                name = "list_apps",
                displayName = "List installed apps",
                description = "List the applications installed on this device.",
                category = ToolCategory.INFORMATION,
                parameters = emptyList(),
                riskLevel = RiskLevel.NONE,
                requiredPermissions = setOf(Permission.PACKAGE_QUERY),
            ),
        ) { _, _ ->
            val apps = device.listInstalledApps()
            ToolOutput(
                summary = "${apps.size} apps installed",
                details = apps.take(20).associate { it.second to it.first },
                data = buildJsonObject {
                    put("count", apps.size)
                },
            )
        }

        registry.register(
            ToolSpec(
                name = "open_settings",
                displayName = "Open system settings",
                description = "Open a specific Android system settings screen.",
                category = ToolCategory.DEVICE,
                parameters = listOf(
                    ToolParameter(
                        "screen", ParamType.STRING, "Settings screen to open",
                        required = true,
                        enumValues = listOf(
                            "wifi", "bluetooth", "battery", "display", "sound", "apps",
                            "location", "security", "storage", "developer", "accessibility",
                            "notification", "home", "root",
                        ),
                    ),
                ),
                riskLevel = RiskLevel.LOW,
                requiredPermissions = setOf(Permission.SYSTEM_SETTINGS),
            ),
        ) { _, args ->
            ToolOutput(device.openSettingsScreen(args.string("screen")))
        }

        registry.register(
            ToolSpec(
                name = "set_alarm",
                displayName = "Set an alarm",
                description = "Create an alarm in the system clock.",
                category = ToolCategory.AUTOMATION,
                parameters = listOf(
                    ToolParameter("hour", ParamType.INTEGER, "Hour in 24-hour format", required = true, minimum = 0.0, maximum = 23.0),
                    ToolParameter("minute", ParamType.INTEGER, "Minute of the hour", required = true, minimum = 0.0, maximum = 59.0),
                    ToolParameter("label", ParamType.STRING, "Optional alarm label", maxLength = 60),
                ),
                riskLevel = RiskLevel.LOW,
                requiredPermissions = setOf(Permission.AUTOMATION),
            ),
        ) { _, args ->
            ToolOutput(
                device.setAlarm(
                    hour = args.int("hour"),
                    minute = args.int("minute"),
                    label = args.string("label"),
                ),
            )
        }

        registry.register(
            ToolSpec(
                name = "call_contact",
                displayName = "Call a contact",
                description = "Open the dialler with a number. The call is placed by the user, not by the app.",
                category = ToolCategory.COMMUNICATION,
                parameters = listOf(
                    ToolParameter("number", ParamType.STRING, "Phone number to dial", required = true, maxLength = 32),
                ),
                riskLevel = RiskLevel.MEDIUM,
                requiredPermissions = setOf(Permission.CONTACTS),
            ),
        ) { _, args ->
            ToolOutput(device.openDialer(args.string("number")))
        }

        registry.register(
            ToolSpec(
                name = "compose_message",
                displayName = "Draft a message",
                description = "Open a messaging app with a pre-filled message for the user to send.",
                category = ToolCategory.COMMUNICATION,
                parameters = listOf(
                    ToolParameter("recipient", ParamType.STRING, "Recipient name or number", maxLength = 80),
                    ToolParameter("body", ParamType.STRING, "Message body", required = true, maxLength = 2000),
                ),
                riskLevel = RiskLevel.HIGH,
                requiresConfirmation = true,
                requiredPermissions = setOf(Permission.CONTACTS),
            ),
        ) { _, args ->
            ToolOutput(device.openMessageComposer(args.string("recipient"), args.string("body")))
        }

        registry.register(
            ToolSpec(
                name = "media_control",
                displayName = "Control media playback",
                description = "Pause, resume or skip the currently playing media.",
                category = ToolCategory.MEDIA,
                parameters = listOf(
                    ToolParameter(
                        "action", ParamType.STRING, "Playback action",
                        required = true,
                        enumValues = listOf("play", "pause", "next", "previous"),
                    ),
                ),
                riskLevel = RiskLevel.LOW,
                requiredPermissions = setOf(Permission.MEDIA_CONTROL),
            ),
        ) { _, args ->
            val action = when (args.string("action")) {
                "play" -> MEDIA_PLAY
                "pause" -> MEDIA_PAUSE
                "next" -> MEDIA_NEXT
                "previous" -> MEDIA_PREVIOUS
                else -> throw IllegalArgumentException("Unknown media action")
            }
            ToolOutput(device.dispatchMediaKey(action))
        }

        registry.register(
            ToolSpec(
                name = "device_diagnostics",
                displayName = "Device diagnostics",
                description = "Report battery, storage, memory and network status of this device.",
                category = ToolCategory.INFORMATION,
                parameters = emptyList(),
                riskLevel = RiskLevel.NONE,
                requiredPermissions = emptySet(),
            ),
        ) { _, _ ->
            val d = device.diagnostics()
            ToolOutput(
                summary = "Battery ${d.batteryPercent ?: "?"}% · Storage ${d.storageFreeGb ?: 0.0} GB free · " +
                    "Network ${d.networkType} · ${d.manufacturer} ${d.model}",
                details = mapOf(
                    "battery" to "${d.batteryPercent ?: "?"}% (${d.batteryHealth ?: "unknown"})",
                    "storage" to "${d.storageUsedGb ?: 0.0} / ${d.storageTotalGb ?: 0.0} GB used",
                    "memory" to "${d.ramUsedGb ?: 0.0} / ${d.ramTotalGb ?: 0.0} GB",
                    "network" to "${d.networkType}${if (d.vpnActive) " (VPN active)" else ""}",
                    "device" to "${d.manufacturer} ${d.model} · Android ${d.osRelease} (SDK ${d.sdkInt})",
                    "uptime" to "${d.uptimeHours} h",
                ),
            )
        }

        registry.register(
            ToolSpec(
                name = "share_text",
                displayName = "Share text",
                description = "Open the system share sheet with a piece of text.",
                category = ToolCategory.DEVICE,
                parameters = listOf(
                    ToolParameter("text", ParamType.STRING, "Text to share", required = true, maxLength = 4000),
                    ToolParameter("subject", ParamType.STRING, "Optional subject", maxLength = 120),
                ),
                riskLevel = RiskLevel.LOW,
                requiredPermissions = emptySet(),
            ),
        ) { _, args ->
            ToolOutput(device.shareText(args.string("text"), args.string("subject")))
        }

        registry.register(
            ToolSpec(
                name = "summarize_notifications",
                displayName = "Summarise notifications",
                description = "Read the notifications posted by other apps and summarise them.",
                category = ToolCategory.INFORMATION,
                parameters = listOf(
                    ToolParameter("limit", ParamType.INTEGER, "Maximum notifications to read", minimum = 1.0, maximum = 50.0),
                ),
                riskLevel = RiskLevel.MEDIUM,
                requiredPermissions = setOf(Permission.NOTIFICATIONS_READ),
            ),
        ) { _, args ->
            val notifications = services.recentNotifications(args.int("limit", 20))
            if (notifications.isEmpty()) {
                ToolOutput("No notifications are currently available.")
            } else {
                ToolOutput(
                    summary = "${notifications.size} notification(s) read",
                    details = notifications.take(12).associate {
                        "${it.appLabel}: ${it.title}" to it.body.take(120)
                    },
                )
            }
        }

        registry.register(
            ToolSpec(
                name = "read_screen",
                displayName = "Read the visible screen",
                description = "Extract the text currently visible on the screen. Requires an active screen-capture consent.",
                category = ToolCategory.INFORMATION,
                parameters = emptyList(),
                riskLevel = RiskLevel.MEDIUM,
                requiredPermissions = setOf(Permission.SCREEN_CAPTURE),
            ),
        ) { _, _ ->
            val text = services.visibleScreenText()
                ?: throw IllegalStateException("No screen-capture consent is active")
            ToolOutput("Screen text extracted (${text.length} characters)", mapOf("text" to text.take(2000)))
        }
    }

    // ------------------------------------------------------------------- files

    private fun registerFileTools() {
        registry.register(
            ToolSpec(
                name = "organize_files",
                displayName = "Organise files",
                description = "Group files in the folder you granted into per-type sub-folders.",
                category = ToolCategory.FILES,
                parameters = listOf(
                    ToolParameter("treeUri", ParamType.STRING, "The granted folder URI", required = true, maxLength = 500),
                    ToolParameter("extension", ParamType.STRING, "Only handle this extension, e.g. pdf", maxLength = 10),
                    ToolParameter("move", ParamType.BOOLEAN, "Remove the originals after a successful copy"),
                ),
                riskLevel = RiskLevel.MEDIUM,
                requiredPermissions = setOf(Permission.FILES),
            ),
        ) { _, args ->
            val uri = android.net.Uri.parse(args.string("treeUri"))
            val message = files.organizeByExtension(
                treeUri = uri,
                extension = args.string("extension"),
                moveConfirmed = args.bool("move") == true,
                dryRun = false,
            )
            ToolOutput(message)
        }

        registry.register(
            ToolSpec(
                name = "list_files",
                displayName = "List files",
                description = "List the files inside the folder you granted.",
                category = ToolCategory.FILES,
                parameters = listOf(
                    ToolParameter("treeUri", ParamType.STRING, "The granted folder URI", required = true, maxLength = 500),
                    ToolParameter("extension", ParamType.STRING, "Filter by extension", maxLength = 10),
                ),
                riskLevel = RiskLevel.LOW,
                requiredPermissions = setOf(Permission.FILES),
            ),
        ) { _, args ->
            val uri = android.net.Uri.parse(args.string("treeUri"))
            val scanned = files.listFiles(uri, args.string("extension"))
            ToolOutput(
                summary = "${scanned.size} file(s) in the granted folder",
                details = scanned.take(20).associate { it.name to "${it.sizeBytes} bytes" },
            )
        }
    }

    // ---------------------------------------------------------------- security

    private fun registerSecurityTools() {
        registry.register(
            ToolSpec(
                name = "network_probe",
                displayName = "Inspect a host",
                description = "Resolve DNS, test TCP reachability and inspect the TLS certificate of a host you own or are authorised to test.",
                category = ToolCategory.SECURITY,
                parameters = listOf(
                    ToolParameter("host", ParamType.STRING, "Hostname or IP address", required = true, maxLength = 255),
                    ToolParameter("port", ParamType.INTEGER, "TCP port", minimum = 1.0, maximum = 65535.0),
                ),
                riskLevel = RiskLevel.MEDIUM,
                requiredPermissions = setOf(Permission.SECURITY_SCAN),
            ),
        ) { _, args ->
            val probe = network.probe(args.string("host"), args.int("port", 443))
            ToolOutput(
                summary = if (probe.reachable) {
                    "${probe.host}:${probe.tcpPort} reachable in ${probe.tcpConnectMs} ms · TLS ${probe.tlsVersion ?: "n/a"}"
                } else {
                    "${probe.host} unreachable: ${probe.error ?: "unknown"}"
                },
                details = buildMap {
                    put("resolved", probe.resolvedAddresses.joinToString(", "))
                    put("dnsMs", "${probe.dnsMs ?: "?"} ms")
                    put("tlsSubject", probe.tlsSubject ?: "n/a")
                    put("tlsIssuer", probe.tlsIssuer ?: "n/a")
                    put("tlsNotAfter", probe.tlsNotAfter ?: "n/a")
                    put("cipher", probe.tlsCipher ?: "n/a")
                    put("chainLength", "${probe.certificateChainLength ?: "?"}")
                },
            )
        }

        registry.register(
            ToolSpec(
                name = "security_review",
                displayName = "Security review",
                description = "Review source or manifest text for defensive security issues and produce remediation advice.",
                category = ToolCategory.SECURITY,
                parameters = listOf(
                    ToolParameter("content", ParamType.STRING, "The source or manifest text to review", required = true, maxLength = 200_000),
                    ToolParameter("fileName", ParamType.STRING, "Name shown in the report", maxLength = 120),
                ),
                riskLevel = RiskLevel.LOW,
                requiredPermissions = setOf(Permission.SECURITY_SCAN),
            ),
        ) { _, args ->
            val result = scanner.scanText(args.string("content"), args.string("fileName", "source.txt"))
            ToolOutput(
                summary = "${result.findings.size} finding(s) across ${result.linesScanned} line(s); " +
                    "highest severity ${result.highest ?: "none"}",
                details = result.findings.associate {
                    it.title to "${it.severity} — ${it.remediation}"
                },
            )
        }
    }

    // -------------------------------------------------------------- development

    private fun registerDevelopmentTools() {
        registry.register(
            ToolSpec(
                name = "code_quality_check",
                displayName = "Code quality check",
                description = "Run static, on-device quality checks over a code snippet. No code is executed.",
                category = ToolCategory.DEVELOPMENT,
                parameters = listOf(
                    ToolParameter("code", ParamType.STRING, "The code to inspect", required = true, maxLength = 100_000),
                    ToolParameter("language", ParamType.STRING, "Programming language", maxLength = 24),
                ),
                riskLevel = RiskLevel.NONE,
                requiredPermissions = setOf(Permission.DEVELOPMENT),
            ),
        ) { _, args ->
            val report = quality.check(args.string("code"), args.string("language", "kotlin"))
            ToolOutput(
                summary = "${report.issues.size} issue(s) in ${report.lines} line(s)",
                details = report.issues.associate { "Line ${it.line}" to it.message },
            )
        }
    }

    // ----------------------------------------------------------------- quantum

    private fun registerQuantumTools() {
        registry.register(
            ToolSpec(
                name = "quantum_simulate",
                displayName = "Run a quantum circuit simulation",
                description = "Simulate a small quantum circuit on the phone's CPU to study gate behaviour.",
                category = ToolCategory.QUANTUM,
                parameters = listOf(
                    ToolParameter(
                        "circuit", ParamType.STRING, "Which built-in circuit to run",
                        required = true,
                        enumValues = listOf("bell", "ghz", "qft2"),
                    ),
                ),
                riskLevel = RiskLevel.NONE,
                requiredPermissions = emptySet(),
            ),
        ) { _, args ->
            val circuit = when (args.string("circuit")) {
                "ghz" -> QuantumSimulator.ghz()
                "qft2" -> QuantumSimulator.quantumFourierTwo()
                else -> QuantumSimulator.bellPair()
            }
            val result = quantum.simulate(circuit)
            ToolOutput(
                summary = "${result.circuitName}: ${result.outcomes.size} outcome(s) in ${result.elapsedMs} ms " +
                    "(classical simulation, no quantum hardware involved)",
                details = result.outcomes.associate { it.bitstring to "p=${"%.3f".format(it.probability)} (${it.count})" },
            )
        }
    }

    // ------------------------------------------------------------------ remote

    private fun registerRemoteTools() {
        registry.register(
            ToolSpec(
                name = "remote_status",
                displayName = "Windows PC status",
                description = "Report whether the paired JARVIS BLUE Windows machine is online and what it is working on.",
                category = ToolCategory.REMOTE,
                parameters = emptyList(),
                riskLevel = RiskLevel.NONE,
                requiredPermissions = setOf(Permission.REMOTE),
            ),
        ) { _, _ ->
            val status = services.remoteStatus()
            ToolOutput(
                summary = "${status.hostname.ifBlank { status.peerId }} is ${status.state.name.lowercase()}",
                details = mapOf(
                    "state" to status.state.name,
                    "runningJobs" to "${status.runningJobs}",
                    "queuedJobs" to "${status.queuedJobs}",
                    "cpu" to "${status.cpuPercent ?: "?"}%",
                    "memory" to "${status.memoryPercent ?: "?"}%",
                    "diskFreeGb" to "${status.diskFreeGb ?: "?"}",
                    "detail" to status.detail,
                ),
            )
        }

        registry.register(
            ToolSpec(
                name = "remote_jobs",
                displayName = "List Windows jobs",
                description = "List the render, project and workflow jobs known to the Windows machine.",
                category = ToolCategory.REMOTE,
                parameters = emptyList(),
                riskLevel = RiskLevel.NONE,
                requiredPermissions = setOf(Permission.REMOTE),
            ),
        ) { _, _ ->
            val jobs = services.remoteJobs()
            ToolOutput(
                summary = "${jobs.size} job(s) on the Windows machine",
                details = jobs.associate { "${it.title} (${it.state.name.lowercase()})" to "${(it.progress * 100).toInt()}%" },
            )
        }

        registry.register(
            ToolSpec(
                name = "remote_submit_job",
                displayName = "Submit a job to the Windows machine",
                description = "Queue an approved task on the paired JARVIS BLUE Windows computer.",
                category = ToolCategory.REMOTE,
                parameters = listOf(
                    ToolParameter("kind", ParamType.STRING, "Job kind", required = true,
                        enumValues = listOf("python", "render", "code_review", "document", "workflow")),
                    ToolParameter("title", ParamType.STRING, "Human readable title", required = true, maxLength = 120),
                    ToolParameter("payload", ParamType.STRING, "JSON payload for the job", maxLength = 20_000),
                ),
                riskLevel = RiskLevel.HIGH,
                requiresConfirmation = true,
                requiredPermissions = setOf(Permission.REMOTE),
            ),
        ) { _, args ->
            val request = com.jarvisblue.core.model.BridgeRequest(
                kind = when (args.string("kind")) {
                    "render" -> com.jarvisblue.core.model.BridgeJobKind.AFTER_EFFECTS_RENDER
                    "python" -> com.jarvisblue.core.model.BridgeJobKind.PYTHON_PROJECT
                    "code_review" -> com.jarvisblue.core.model.BridgeJobKind.CODE_REVIEW
                    "document" -> com.jarvisblue.core.model.BridgeJobKind.DOCUMENT_ACCESS
                    else -> com.jarvisblue.core.model.BridgeJobKind.WORKFLOW
                },
                title = args.string("title"),
                payloadJson = args.string("payload", "{}"),
                requireApproval = true,
            )
            val job = services.submitRemoteJob(request)
            ToolOutput("Queued '${job.title}' on the Windows machine (id ${job.id})")
        }

        registry.register(
            ToolSpec(
                name = "remote_cancel_job",
                displayName = "Cancel a Windows job",
                description = "Cancel a running or queued job on the Windows machine.",
                category = ToolCategory.REMOTE,
                parameters = listOf(
                    ToolParameter("jobId", ParamType.STRING, "Identifier of the job", required = true, maxLength = 120),
                ),
                riskLevel = RiskLevel.HIGH,
                requiresConfirmation = true,
                requiredPermissions = setOf(Permission.REMOTE),
            ),
        ) { _, args ->
            val ok = services.cancelRemoteJob(args.string("jobId"))
            ToolOutput(if (ok) "Job cancelled" else "Job could not be cancelled")
        }
    }
}

// ------------------------------------------------------------------ helpers

internal fun JsonObject.string(key: String, default: String = ""): String =
    (this[key] as? JsonPrimitive)?.content ?: default

internal fun JsonObject.int(key: String, default: Int = 0): Int =
    (this[key] as? JsonPrimitive)?.content?.toDoubleOrNull()?.toInt() ?: default

internal fun JsonObject.bool(key: String): Boolean =
    (this[key] as? JsonPrimitive)?.content?.toBooleanStrictOrNull() ?: false
