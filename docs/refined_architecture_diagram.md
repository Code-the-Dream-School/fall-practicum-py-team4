# City Air Tracker - System Architecture & Plan

This document outlines the system architecture and data flow for the **City Air Tracker** project, detailing how data moves from input through raw and gold PostgreSQL storage, powers the Streamlit dashboard, and maps to an eventual AWS cloud deployment.

## System Architecture Diagram

The diagram below illustrates the major local components and connections of the system:

```mermaid
graph TD
    %% Input Configuration & Sources
    subgraph Input_Config [1. Input Configuration & Sources]
        A1[City List] --> A2[(PostgreSQL)]
        A2 --> A3[Geocoding Cache Lat/Lon]
    end

    subgraph Data_Source_Extract [2. Data Source & Extract]
        A3 --> B1[Python Extract Script]
        B1 --> B2[OpenWeather Geocoding API]
        B1 --> B3[OpenWeather Air Pollution API]
    end

    subgraph Raw_Storage [3. Raw Storage]
        B3 --> C1[(PostgreSQL Raw Data)]
    end

    subgraph Transform_Gold [4. Transform & Gold Storage]
        C1 --> D1[Python <br> Transform Logic]
        D1 --> D2[(PostgreSQL <br>Gold Dataset)]
    end

    subgraph Orchestration [5. Orchestrated Flow]
        E1[Orchestration <br/> Prefect] -.->|Triggers| B1
    end

    subgraph Dashboard_API [6. Consumption & Dashboard]
        D2 --> F1[Streamlit Dashboard]
    end
```

## Component Breakdown

1. **Input Configuration**
   - **City List:** List of target global cities stored as runtime state.
   - **Geocoding Cache:** Prevents redundant external calls by saving resolved latitude and longitude values in PostgreSQL.

2. **Data Source and `extract()`**
   - **OpenWeather APIs:** Feeds raw location and historical air pollution data.
   - **Python Extractor:** Queries APIs and captures raw responses.

3. **Raw Storage**
   - **PostgreSQL Raw Tables:** Stores immutable, raw response records before any data cleaning.

4. **`transform()` and Gold Storage**
   - **Transformation Logic:** Cleans, parses, and structures raw records.
   - **Gold Dataset:** Normalized or aggregated tables in PostgreSQL for downstream consumption.

5. **Orchestrated Flow**
   - **Orchestration:** Coordinates the execution sequence from ingestion to transformation, via Prefect.

6. **Dashboard**
   - **Streamlit Dashboard:** Displays historical air quality metrics, interactive charts, and city trends.

## Eventual AWS Deployment

The following diagram illustrates the system transitioned to an eventual AWS deployment:

```mermaid
graph TD
    %% Sources
    subgraph Sources [External Sources]
        A1[City List / Database]
        A2[OpenWeather APIs]
    end

    %% AWS Cloud Environment
    subgraph AWS_Cloud [AWS Cloud Architecture]
        
        %% Scheduling & Monitoring
        EB[Amazon EventBridge <br/> Scheduled Trigger] -->|Triggers hourly/daily| L1
        
        %% Compute (Extract & Transform)
        subgraph Compute
            L1[AWS Lambda <br/> Python Extract & Transform]
        end
        
        %% Storage
        subgraph Storage
            RDS[(Amazon RDS <br/> PostgreSQL Database)]
        end
        
        %% Consumption
        subgraph Frontend
            FE[Amazon EC2 / S3 <br/> Streamlit Dashboard]
        end
        
        %% Monitoring
        L1 -.->|Logs & Metrics| CW[Amazon CloudWatch]
    end

    %% Data Flows
    A1 --> L1
    A2 -->|Fetch weather data| L1
    L1 -->|Save raw & gold data| RDS
    RDS -->|Query data| FE
```

### AWS Deployment Components

- **Database:** Transition from local PostgreSQL to **Amazon RDS for PostgreSQL**.
- **Compute & Orchestration:** Serverless batch pipeline running on **AWS Lambda**, triggered on a schedule by **Amazon EventBridge**.
- **App Hosting:** **Amazon EC2 / S3 / ECS** to host and run the interactive Streamlit dashboard application.
- **Observability:** Pipeline execution logs, metrics, and error monitoring managed through **Amazon CloudWatch**.