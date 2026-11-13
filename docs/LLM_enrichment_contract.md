# LLM Enrichment — Air Quality Summary

## 1. Purpose

The LLM will generate a short, human-readable summary of air quality conditions for a city using the features available in the gold dataset.

The summary will explain the air quality measurements in understandable language, including the overall AQI, pollutant concentrations, and available rolling averages.

The LLM will only interpret existing data, not calculate new measurements or change existing values.

## 2. Records to Enrich

**Enriched records:**
- Gold air quality records containing a valid AQI value (1–5).
- Records containing at least one available pollutant measurement.

**Skipped records:**
- Records without a valid AQI.
- Records without any available pollutant measurements.
- Records that already have a summary for the same unchanged measurements.

Missing optional features, such as rolling averages, will not prevent enrichment.

## 3. Fields Added

| Field | Type | Allowed Values |
|---|---|---|
| `llm_summary` | TEXT, nullable | Plain-language summary, 1–3 sentences, maximum 500 characters |

The summary will be stored alongside the corresponding gold air quality record.

A NULL value indicates that enrichment was skipped or unsuccessful.

## 4. Prompt Instructions

The prompt will be stored in a separate file:

`prompts/air_quality_summary.txt`

**Prompt:**

You are an assistant that summarizes air quality data for a dashboard.

Using only the provided air quality measurements, generate a clear, concise summary of the conditions.

Available features may include:
- AQI (1–5)
- Sentiment label (Good, Fair, Moderate, Poor, Very Poor)
- Pollutant concentrations (CO and PM2_5)
- Seven-day rolling averages for AQI and PM2.5

Instructions:
1. Write 1–3 sentences in plain English.
2. Describe the overall air quality conditions.
3. Mention relevant pollutant measurements when available.
4. Discuss rolling averages only when provided.
5. Do not invent missing measurements.
6. Do not make unsupported health claims.
7. Do not calculate or modify AQI values.
8. Return only the summary text.
9. Assume measurments in μg/m³ and PM2_5 is the same as PM2.5

## 5. Invalid or Unusable Responses

If the LLM returns an empty, malformed, or unusable response:

1. Validate that the response contains nonempty text within the 500-character limit.
2. Reject responses that contain unexpected formats or unsupported information.
3. Retry the request once if validation fails.
4. If the second attempt fails, leave `llm_summary` as NULL.
5. Log the failure for debugging without interrupting the rest of the pipeline.

Existing air quality measurements must remain unchanged if enrichment fails.

## 6. Example

**Input:**

- AQI: 3
- Sentiment: Moderate
- PM2_5: 18.5 
- CO: 240 
- Seven-day AQI average: 2.7
- Seven-day PM2.5 average: 16.2 

**Expected output:**

"Air quality is currently moderate, with an AQI of 3. PM2.5 is measured at 18.5 μg/m³, slightly above its seven-day average of 16.2 μg/m³. The seven-day AQI average of 2.7 provides additional context for recent conditions."