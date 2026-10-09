from typing import Generator
from sqlmodel import SQLModel, Session, create_engine
from app.config import DATABASE_URL

# SQLite connect args to allow multithreading safely
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def init_db() -> None:
    """Initialize database tables and run automatic migrations if needed."""
    SQLModel.metadata.create_all(engine)
    
    # Auto-migrate missing columns for SQLite
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            # Check form_records columns
            result = conn.execute(text("PRAGMA table_info(form_records)")).fetchall()
            existing_cols = {row[1] for row in result}
            
            columns_to_add = [
                ("document_type", "VARCHAR DEFAULT 'CUSTOMER_REQUEST_FORM'"),
                ("is_valid_crf", "BOOLEAN DEFAULT 1"),
                ("validation_message", "VARCHAR"),
                ("raw_extracted_text", "VARCHAR"),
            ]
            for col_name, col_def in columns_to_add:
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE form_records ADD COLUMN {col_name} {col_def}"))
            
            # Check form_pages columns
            page_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(form_pages)")).fetchall()}
            if "ocr_text" not in page_cols:
                conn.execute(text("ALTER TABLE form_pages ADD COLUMN ocr_text VARCHAR"))
                
            conn.commit()
    except Exception as e:
        print(f"Database migration notice: {e}")


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions."""
    with Session(engine) as session:
        yield session
