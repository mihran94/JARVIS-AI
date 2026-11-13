package com.jarvisblue.core.tools

import com.jarvisblue.core.model.ParamType
import com.jarvisblue.core.model.ToolSpec
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Validates tool arguments against the declarative [ToolSpec].
 *
 * This is the hard boundary between "the model asked for something" and
 * "something is about to run". Unknown properties are rejected outright, so a
 * model cannot smuggle extra parameters past the schema.
 */
object SchemaValidator {

    sealed interface Result {
        data class Valid(val normalized: JsonObject) : Result
        data class Invalid(val errors: List<String>) : Result
    }

    fun validate(spec: ToolSpec, arguments: JsonObject): Result {
        val errors = mutableListOf<String>()

        val declared = spec.parameters.associateBy { it.name }
        val unknown = arguments.keys - declared.keys
        if (unknown.isNotEmpty()) {
            errors += "Unknown parameter(s): ${unknown.sorted().joinToString(", ")}"
        }

        val normalized = mutableMapOf<String, JsonElement>()

        for (parameter in spec.parameters) {
            val value = arguments[parameter.name]
            if (value == null || value is JsonNull) {
                if (parameter.required) {
                    errors += "Missing required parameter '${parameter.name}'"
                } else if (parameter.default != null) {
                    normalized[parameter.name] = JsonPrimitive(parameter.default)
                }
                continue
            }

            val typeError = checkType(parameter.type, value)
            if (typeError != null) {
                errors += "Parameter '${parameter.name}' expects ${parameter.type.name.lowercase()} but got $typeError"
                continue
            }

            if (parameter.enumValues.isNotEmpty() && value is JsonPrimitive && value.isString) {
                if (value.content !in parameter.enumValues) {
                    errors += "Parameter '${parameter.name}' must be one of: ${parameter.enumValues.joinToString(", ")}"
                    continue
                }
            }

            val maxLength = parameter.maxLength
            if (maxLength != null && value is JsonPrimitive && value.content.length > maxLength) {
                errors += "Parameter '${parameter.name}' exceeds max length $maxLength"
                continue
            }

            if (value is JsonPrimitive) {
                val numeric = value.content.toDoubleOrNull()
                if (numeric != null) {
                    val minimum = parameter.minimum
                    val maximum = parameter.maximum
                    if (minimum != null && numeric < minimum) {
                        errors += "Parameter '${parameter.name}' is below the minimum $minimum"
                        continue
                    }
                    if (maximum != null && numeric > maximum) {
                        errors += "Parameter '${parameter.name}' is above the maximum $maximum"
                        continue
                    }
                }
            }

            normalized[parameter.name] = value
        }

        return if (errors.isEmpty()) Result.Valid(JsonObject(normalized)) else Result.Invalid(errors)
    }

    private fun checkType(type: ParamType, value: JsonElement): String? {
        val primitive = value as? JsonPrimitive
        return when (type) {
            ParamType.STRING ->
                if (primitive != null && primitive.isString) null else "a string"
            ParamType.INTEGER ->
                if (primitive != null && !primitive.isString && primitive.content.toDoubleOrNull()?.let {
                        it == Math.floor(it) && !it.isInfinite()
                    } == true
                ) null else "an integer"
            ParamType.NUMBER ->
                if (primitive != null && !primitive.isString && primitive.content.toDoubleOrNull() != null) {
                    null
                } else "a number"
            ParamType.BOOLEAN ->
                if (primitive != null && !primitive.isString &&
                    (primitive.content == "true" || primitive.content == "false")
                ) null else "a boolean"
            ParamType.OBJECT ->
                if (value is JsonObject) null else "an object"
            ParamType.ARRAY ->
                if (value is JsonArray) null else "an array"
        }
    }
}
