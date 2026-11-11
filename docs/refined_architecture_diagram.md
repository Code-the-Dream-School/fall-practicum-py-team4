# City Air Tracker - System Architecture & Plan

This document outlines the system architecture and data flow for the **City Air Tracker** project, detailing how data moves from input through raw and gold PostgreSQL storage, powers the Streamlit dashboard, and maps to an eventual AWS cloud deployment.

## System Architecture Diagram

The diagram below illustrates the major local components and connections of the system:

```mermaid
graph TD
    classDef table stroke:#01579b,stroke-width:2px;
    classDef api stroke:#2e7d32,stroke-width:2px;
    classDef process stroke:#e65100,stroke-width:2px;

    %% 1. Input & Orchestration
    Start([City List]) --> Orch[<b>Orchestration</b><br>Prefect]
    
    %% Pipeline Run Logging
    Orch --> LogRun[<b>Log Run</b><br>Record Execution Metadata]:::process
    LogRun --> PR[(<b>Load</b><br>Supabase<br>pipeline_runs)]:::table

    %% 2. Geocoding Cache Check
    Orch --> CheckDB{<b>Geocoding Cache</b><br>Exists in gold_cities?}:::process
    
    %% 3. API & Transformation (If Cache Miss)
    CheckDB -- No --> OM[<b>Extract</b><br>Open-Meteo Geocoding API]:::api
    OM --> TransCity[<b>Transform</b><br>Geocoding Data]:::process
    TransCity --> GC[(<b>Load</b><br>Supabase<br>gold_cities)]:::table
    
    %% 4. Cache Hit Path
    CheckDB -- Yes --> GC
    
    %% 5. Air Pollution Extraction & Transformation
    GC --> OW[<b>Extract</b><br>OpenWeather Air Pollution API]:::api
    OW --> TransAir[<b>Transform</b><br> Air Data]:::process
    TransAir --> GA[(<b>Load</b><br>Supabase<br>gold_air_data)]:::table
    
    %% 6. Dashboard Consumption
    GC --> Dash[Streamlit Dashboard]
    GA --> Dash
```

## Component Breakdown

1. **City List:**
   List of target global cities.


2. **Orchestration**
   Coordinates the execution sequence from ingestion to transformation, via Prefect.

3. **Logging**
   Tracks and records execution metadata (such as run status, timestamps, and execution details) for every pipeline run into the pipeline_runs table for auditing and monitoring.

4. **Geocoding Cache**
   Prevents redundant external calls by saving resolved latitude and longitude values.

5. **Data Source and Extract**
- **OpenMeteo API:** Feeds raw geocoding, population and elevation data.
   - **OpenWeather API:** Feeds raw historical air pollution data.
   - **Extraction:** Queries APIs and captures raw responses.

6. **Raw Storage**
   - **Supabase:** Stores immutable, raw response records before any data cleaning.

7. **`Transform and Gold Storage**
   - **Transformation Logic:** Cleans, parses, and structures raw records.
   - **Gold Dataset:** Normalized or aggregated tables in Supabase for downstream consumption.

8. **Dashboard**
   - **Streamlit Dashboard:** Displays historical air quality metrics, interactive charts, and city trends.

## Eventual AWS Deployment

The following diagram illustrates the system transitioned to an eventual AWS deployment:

```mermaid
graph TD
    classDef table stroke:#01579b,stroke-width:2px;
    classDef api stroke:#2e7d32,stroke-width:2px;
    classDef process stroke:#e65100,stroke-width:2px;

    %% Sources
    subgraph Sources [External Sources]
        A1[City List]
        A2[Open-Meteo Geocoding API]:::api
        A3[OpenWeather Air Pollution API]:::api
    end

    %% AWS Cloud Environment
    subgraph AWS_Cloud [AWS Cloud Architecture]
        
        %% Scheduling & Trigger
        EB[Amazon EventBridge <br/> Scheduled Trigger] -->|Triggers execution| L1
        
        %% Compute (Extract & Transform)
        subgraph Compute
            L1[AWS Lambda <br/> Prefect]:::process
        end
        
        %% Monitoring
        L1 -.->|Infrastructure Logs| CW[Amazon CloudWatch]
    end

    %% External Database (Supabase)
    subgraph Supabase_Cloud [External Database & Storage]
        RDS[(Supabase <br/> gold_cities & gold_air_data)]:::table
        PR[(Supabase <br/> pipeline_runs)]:::table
    end

    %% Consumption
    subgraph Frontend [Presentation Layer]
        FE[Streamlit Dashboard]
    end

    %% Data Flows
    A1 -->|Input city| L1
    
    %% Pipeline Run Logging Flow
    L1 -->|Log execution metadata| PR
    
    %% Cache Check Flow
    L1 -->|1. Check gold_cities cache| RDS
    RDS -->|Cache Miss / Not Found| A2
    A2 -->|Fresh geocoding payload| L1
    L1 -->|Save raw & gold city data| RDS
    
    %% Air Pollution Ingestion Flow (Uses coordinates from cache or fresh fetch)
    RDS -->|Provide coordinates| L1
    A3 -->|Fetch air history| L1
    L1 -->|Save raw & gold air data| RDS
    
    %% Dashboard Consumption
    RDS -->|Query Gold layers| FE
```

### AWS Deployment Components

- **Database:** Supabase, housing raw data, gold data, and audit tables.
- **Compute & Orchestration:** Serverless batch pipeline running on **AWS Lambda**, triggered on a schedule by **Amazon EventBridge**, executing the Prefect with cache-aside geocoding logic.
- **App Hosting:** **Amazon EC2 / S3 / ECS** to host and run the interactive Streamlit dashboard application.
- **Observability:** Pipeline execution logs, metrics, and error monitoring managed through **Amazon CloudWatch**.