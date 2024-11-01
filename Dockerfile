FROM python:3.12.7 AS python

WORKDIR /app

COPY . .

RUN python -m pip install -r requirements.txt

CMD ["python", "."]
