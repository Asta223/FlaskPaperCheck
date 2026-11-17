-- FlaskPaperCheck 数据库初始化脚本（MySQL）
-- 在 MySQL 命令行或客户端执行：
--   mysql -u root -p < setup.sql

CREATE DATABASE IF NOT EXISTS `paper_check`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE `paper_check`;

-- 如需单独账号（把密码改成你自己的）：
-- CREATE USER IF NOT EXISTS 'paper'@'localhost' IDENTIFIED BY 'paper_pass';
-- GRANT ALL PRIVILEGES ON `paper_check`.* TO 'paper'@'localhost';
-- FLUSH PRIVILEGES;
