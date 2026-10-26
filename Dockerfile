FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PORT=7860
WORKDIR /app
COPY . /app
# 외부 패키지 의존성이 없어 pip install 단계가 필요 없다
RUN useradd -m appuser && chown -R appuser /app
USER appuser
EXPOSE 7860
CMD ["python", "server.py"]
