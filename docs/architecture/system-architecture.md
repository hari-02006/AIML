# System Architecture

## Overall Architecture
The system follows a modular architecture integrating front-end, back-end, operational database, data pipelines, ML, and AI.

```text
                SMART INVENTORY SYSTEM
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
       FRONTEND       BACKEND       DATABASE
        React          FastAPI      PostgreSQL
          |              |              |
          +--------------+--------------+
                         |
                         v
                 ANALYTICS LAYER
                         |
               +---------+---------+
               |                   |
               v                   v
           DASHBOARD          ML PIPELINE
                                   |
                                   v
                            DEMAND FORECAST
                                   |
                                   v
                          INVENTORY ENGINE
                                   |
                     +-------------+-------------+
                     |                           |
                     v                           v
              REORDER DECISION             STOCKOUT RISK
                     |
                     v
                AI ASSISTANT
                     |
                     v
             HUMAN EXPLANATION
```

## Layers

### Frontend Layer
- **Technology**: React
- **Responsibility**: Present dashboard, visualize inventory levels, surface reorder recommendations and AI explanations to users.

### Backend Layer
- **Technology**: FastAPI (Python)
- **Responsibility**: Expose REST APIs for the frontend, integrate with the database, trigger ML models, and communicate with the AI layer.

### Database Layer
- **Technology**: PostgreSQL
- **Responsibility**: Store operational data (products, sales, inventory) and serve as the main persistence layer.

### Data-Generator Layer
- **Technology**: Python (Pandas/NumPy)
- **Responsibility**: Create synthetic e-commerce sales and inventory data for the project.

### ETL Layer
- **Technology**: Python, Pandas, SQL
- **Responsibility**: Extract generated data, validate it, transform it into proper schema, and load it into PostgreSQL.

### Analytics Layer
- **Technology**: SQL, Pandas, Plotly
- **Responsibility**: Compute historical trends and business metrics (sales volume, stockout frequency).

### ML Layer
- **Technology**: scikit-learn, XGBoost
- **Responsibility**: Perform feature engineering on historical data and train models to predict next-day demand.

### Inventory Layer
- **Technology**: Python
- **Responsibility**: Calculate reorder points, safety stock, and recommend order quantities based on ML predictions.

### AI Layer
- **Technology**: Ollama (local LLM)
- **Responsibility**: Consume inventory state and decisions to generate human-readable explanations.

### Future Data Warehouse
*(Not implemented in Stage 0)*
- Eventually, a separate analytical data warehouse may be introduced for complex OLAP queries.

## Flows

### Data Flow
1. Data Generator creates Raw Data.
2. ETL pipeline Extracts, Transforms, Validates, and Loads data into PostgreSQL.

### API Flow
1. Frontend makes HTTP requests to FastAPI.
2. FastAPI queries PostgreSQL or calls ML/AI services.
3. Response is sent back to the Frontend.

### ML Flow
1. Fetch data from DB.
2. Compute features (lags, rolling averages).
3. Generate demand prediction.
4. Pass prediction to Inventory engine.

### Future Deployment Flow
- Docker containers for each component, optionally orchestrated by Airflow for data pipelines.
