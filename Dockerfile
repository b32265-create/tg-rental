FROM python:3.11-slim

# Set timezone
ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything else
COPY . .

# Hugging Face Spaces require the app to bind to port 7860 to stay healthy
ENV PORT=7860
EXPOSE 7860

# Run the bot
CMD ["python", "main.py"]
