package com.jarvisblue.core.tools

import com.jarvisblue.core.model.MemoryKind
import com.jarvisblue.core.model.Permission
import com.jarvisblue.core.model.RiskLevel
import com.jarvisblue.core.model.ToolCategory
import com.jarvisblue.core.model.ToolParameter
import com.jarvisblue.core.model.ToolSpec
import com.jarvisblue.core.model.ParamType
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Personal-memory tools backed by the encrypted database. */
class MemoryTools(
    private val repository: com.jarvisblue.core.database.MemoryRepository,
) {

    fun register(registry: ToolRegistry) {
        registry.register(
            ToolSpec(
                name = "remember",
                displayName = "Remember a fact",
                description = "Store a durable note about the user so future conversations can use it.",
                category = ToolCategory.MEMORY,
                parameters = listOf(
                    ToolParameter("title", ParamType.STRING, "Short label for the memory", required = true, maxLength = 120),
                    ToolParameter("body", ParamType.STRING, "The detail to remember", required = true, maxLength = 4000),
                    ToolParameter("kind", ParamType.STRING, "Kind of memory",
                        enumValues = listOf("PROFILE", "PREFERENCE", "FACT", "PROCEDURE")),
                ),
                riskLevel = RiskLevel.LOW,
                requiredPermissions = setOf(Permission.MEMORY_STORE),
            ),
        ) { _, args ->
            val kind = runCatching { MemoryKind.valueOf(args.string("kind").uppercase()) }
                .getOrDefault(MemoryKind.FACT)
            val item = repository.remember(
                kind = kind,
                title = args.string("title"),
                body = args.string("body"),
            )
            ToolOutput("Remembered '${item.title}'")
        }

        registry.register(
            ToolSpec(
                name = "recall",
                displayName = "Recall memories",
                description = "Search the personal memory store for notes relevant to a query.",
                category = ToolCategory.MEMORY,
                parameters = listOf(
                    ToolParameter("query", ParamType.STRING, "Search term", required = true, maxLength = 200),
                    ToolParameter("limit", ParamType.INTEGER, "Maximum results", minimum = 1.0, maximum = 50.0),
                ),
                riskLevel = RiskLevel.NONE,
                requiredPermissions = setOf(Permission.MEMORY_STORE),
            ),
        ) { _, args ->
            val limit = args.int("limit", 10)
            val items = repository.search(args.string("query"), limit).ifEmpty {
                repository.contextWindow(limit)
            }
            ToolOutput(
                summary = "${items.size} memory item(s) recalled",
                details = items.associate { it.title to it.body.take(200) },
                data = buildJsonObject { put("count", items.size) },
            )
        }
    }
}
