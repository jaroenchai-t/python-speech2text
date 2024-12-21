# Use Python 3.9 slim as base image
FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime
 
# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install dependencies
RUN apt-get update && apt-get install -y \
    wget \
    xz-utils \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create directories
RUN mkdir -p /app/models/huggingface /app/data /app/logs

# Upgrade pip
RUN pip install --upgrade pip

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies with cache mounting
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY . .

# Configure Streamlit
ENV STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Remove the user creation and switching
# RUN useradd -m -r streamlit
# RUN chown -R streamlit:streamlit /app
# USER streamlit  <- Remove this line

EXPOSE 8501

VOLUME ["/app/models", "/app/data", "/app/logs"]

CMD ["streamlit", "run", "app.py"]