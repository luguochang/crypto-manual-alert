-- 创建 langfuse 数据库（与 app 的 crypto_alert 数据库隔离）
CREATE DATABASE langfuse;
GRANT ALL PRIVILEGES ON DATABASE langfuse TO agent;
