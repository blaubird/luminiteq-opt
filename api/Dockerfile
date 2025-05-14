# Base image for Python
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file first to leverage Docker cache
COPY ./requirements.txt /app/requirements.txt

# Install pip-tools if it needs to be available in the build image (optional, usually for compiling)
# RUN python -m pip install pip-tools

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . /app

# Expose the port the app runs on (FastAPI default is 8000 if not specified otherwise by Hypercorn/Uvicorn)
EXPOSE 8000

# Command to run the application using Hypercorn (as per original README)
# The original main.py was in the root of /api, so main:app should work.
# Ensure your Procfile or Railway start command uses a similar command.
CMD ["hypercorn", "main:app", "--bind", "0.0.0.0:8000"]

