-- MySQL dump 10.13  Distrib 5.5.11, for Win32 (x86)
--
-- Host: 127.0.0.1    Database: factory manager
-- ------------------------------------------------------
-- Server version	5.5.11

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `alembic_version`
--

DROP TABLE IF EXISTS `alembic_version`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alembic_version`
--

LOCK TABLES `alembic_version` WRITE;
/*!40000 ALTER TABLE `alembic_version` DISABLE KEYS */;
INSERT INTO `alembic_version` VALUES ('a1b2c3d4e5f6');
/*!40000 ALTER TABLE `alembic_version` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `attendance_records`
--

DROP TABLE IF EXISTS `attendance_records`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `attendance_records` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL COMMENT '员工',
  `work_date` date NOT NULL COMMENT '打卡日期',
  `check_in_at` datetime DEFAULT NULL COMMENT '签到时间',
  `check_out_at` datetime DEFAULT NULL COMMENT '签退时间',
  `late_minutes` int(11) NOT NULL DEFAULT '0' COMMENT '迟到分钟数',
  `early_leave_minutes` int(11) NOT NULL DEFAULT '0' COMMENT '早退分钟数',
  `day_status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'normal' COMMENT '日状态短码',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_attendance_user_date` (`user_id`,`work_date`),
  CONSTRAINT `attendance_records_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=573 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `attendance_records`
--

LOCK TABLES `attendance_records` WRITE;
/*!40000 ALTER TABLE `attendance_records` DISABLE KEYS */;
INSERT INTO `attendance_records` VALUES (287,2,'2026-11-17','2026-11-17 09:12:00','2026-11-17 18:05:00',12,0,'late'),(288,2,'2026-11-16','2026-11-16 08:55:00','2026-11-16 17:40:00',0,20,'early'),(289,2,'2026-11-13','2026-11-13 08:50:00','2026-11-13 18:10:00',0,0,'normal'),(290,2,'2026-11-12','2026-11-12 08:50:00','2026-11-12 18:10:00',0,0,'normal'),(291,2,'2026-11-11','2026-11-11 08:50:00','2026-11-11 18:10:00',0,0,'normal'),(292,2,'2026-11-10','2026-11-10 08:50:00','2026-11-10 18:10:00',0,0,'normal'),(293,2,'2026-11-09','2026-11-09 08:50:00','2026-11-09 18:10:00',0,0,'normal'),(294,2,'2026-11-06','2026-11-06 08:55:00','2026-11-06 17:40:00',0,20,'early'),(295,2,'2026-11-05','2026-11-05 09:25:00','2026-11-05 17:30:00',12,20,'late,early'),(296,2,'2026-11-04','2026-11-04 08:50:00','2026-11-04 18:10:00',0,0,'normal'),(297,2,'2026-11-03','2026-11-03 08:50:00','2026-11-03 18:10:00',0,0,'normal'),(298,2,'2026-11-02','2026-11-02 08:50:00','2026-11-02 18:10:00',0,0,'normal'),(299,2,'2026-10-30','2026-10-30 08:50:00','2026-10-30 18:10:00',0,0,'normal'),(300,2,'2026-10-29',NULL,NULL,0,0,'leave'),(301,2,'2026-10-28','2026-10-28 09:12:00','2026-10-28 18:05:00',12,0,'late'),(302,2,'2026-10-27','2026-10-27 08:55:00','2026-10-27 17:40:00',0,20,'early'),(303,2,'2026-10-26','2026-10-26 09:25:00','2026-10-26 17:30:00',12,20,'late,early'),(304,2,'2026-10-23','2026-10-23 08:50:00','2026-10-23 18:10:00',0,0,'normal'),(305,2,'2026-10-22','2026-10-22 08:50:00','2026-10-22 18:10:00',0,0,'normal'),(306,2,'2026-10-21','2026-10-21 08:50:00','2026-10-21 18:10:00',0,0,'normal'),(307,2,'2026-10-20','2026-10-20 08:50:00','2026-10-20 18:10:00',0,0,'normal'),(308,2,'2026-10-19',NULL,NULL,0,0,'leave'),(309,3,'2026-11-17','2026-11-17 08:55:00','2026-11-17 17:40:00',0,20,'early'),(310,3,'2026-11-16','2026-11-16 09:25:00','2026-11-16 17:30:00',12,20,'late,early'),(311,3,'2026-11-13','2026-11-13 08:50:00','2026-11-13 18:10:00',0,0,'normal'),(312,3,'2026-11-12','2026-11-12 08:50:00','2026-11-12 18:10:00',0,0,'normal'),(313,3,'2026-11-11','2026-11-11 08:50:00','2026-11-11 18:10:00',0,0,'normal'),(314,3,'2026-11-10','2026-11-10 08:50:00','2026-11-10 18:10:00',0,0,'normal'),(315,3,'2026-11-09',NULL,NULL,0,0,'leave'),(316,3,'2026-11-06','2026-11-06 09:25:00','2026-11-06 17:30:00',12,20,'late,early'),(317,3,'2026-11-05','2026-11-05 08:50:00','2026-11-05 18:10:00',0,0,'normal'),(318,3,'2026-11-04','2026-11-04 08:50:00','2026-11-04 18:10:00',0,0,'normal'),(319,3,'2026-11-03','2026-11-03 08:50:00','2026-11-03 18:10:00',0,0,'normal'),(320,3,'2026-11-02','2026-11-02 08:50:00','2026-11-02 18:10:00',0,0,'normal'),(321,3,'2026-10-30',NULL,NULL,0,0,'leave'),(322,3,'2026-10-29','2026-10-29 09:12:00','2026-10-29 18:05:00',12,0,'late'),(323,3,'2026-10-28','2026-10-28 08:55:00','2026-10-28 17:40:00',0,20,'early'),(324,3,'2026-10-27','2026-10-27 09:25:00','2026-10-27 17:30:00',12,20,'late,early'),(325,3,'2026-10-26','2026-10-26 08:50:00','2026-10-26 18:10:00',0,0,'normal'),(326,3,'2026-10-23','2026-10-23 08:50:00','2026-10-23 18:10:00',0,0,'normal'),(327,3,'2026-10-22','2026-10-22 08:50:00','2026-10-22 18:10:00',0,0,'normal'),(328,3,'2026-10-21','2026-10-21 08:50:00','2026-10-21 18:10:00',0,0,'normal'),(329,3,'2026-10-20',NULL,NULL,0,0,'leave'),(330,3,'2026-10-19','2026-10-19 09:12:00','2026-10-19 18:05:00',12,0,'late'),(331,4,'2026-11-17','2026-11-17 09:25:00','2026-11-17 17:30:00',12,20,'late,early'),(332,4,'2026-11-16','2026-11-16 08:50:00','2026-11-16 18:10:00',0,0,'normal'),(333,4,'2026-11-13','2026-11-13 08:50:00','2026-11-13 18:10:00',0,0,'normal'),(334,4,'2026-11-12','2026-11-12 08:50:00','2026-11-12 18:10:00',0,0,'normal'),(335,4,'2026-11-11','2026-11-11 08:50:00','2026-11-11 18:10:00',0,0,'normal'),(336,4,'2026-11-10',NULL,NULL,0,0,'leave'),(337,4,'2026-11-09','2026-11-09 09:12:00','2026-11-09 18:05:00',12,0,'late'),(338,4,'2026-11-06','2026-11-06 08:50:00','2026-11-06 18:10:00',0,0,'normal'),(339,4,'2026-11-05','2026-11-05 08:50:00','2026-11-05 18:10:00',0,0,'normal'),(340,4,'2026-11-04','2026-11-04 08:50:00','2026-11-04 18:10:00',0,0,'normal'),(341,4,'2026-11-03','2026-11-03 08:50:00','2026-11-03 18:10:00',0,0,'normal'),(342,4,'2026-11-02','2026-11-02 08:50:00','2026-11-02 18:10:00',0,0,'normal'),(343,4,'2026-10-30','2026-10-30 09:12:00','2026-10-30 18:05:00',12,0,'late'),(344,4,'2026-10-29','2026-10-29 08:55:00','2026-10-29 17:40:00',0,20,'early'),(345,4,'2026-10-28','2026-10-28 09:25:00','2026-10-28 17:30:00',12,20,'late,early'),(346,4,'2026-10-27','2026-10-27 08:50:00','2026-10-27 18:10:00',0,0,'normal'),(347,4,'2026-10-26','2026-10-26 08:50:00','2026-10-26 18:10:00',0,0,'normal'),(348,4,'2026-10-23','2026-10-23 08:50:00','2026-10-23 18:10:00',0,0,'normal'),(349,4,'2026-10-22','2026-10-22 08:50:00','2026-10-22 18:10:00',0,0,'normal'),(350,4,'2026-10-21',NULL,NULL,0,0,'leave'),(351,4,'2026-10-20','2026-10-20 09:12:00','2026-10-20 18:05:00',12,0,'late'),(352,4,'2026-10-19','2026-10-19 08:55:00','2026-10-19 17:40:00',0,20,'early'),(353,5,'2026-11-17','2026-11-17 08:50:00','2026-11-17 18:10:00',0,0,'normal'),(354,5,'2026-11-16','2026-11-16 08:50:00','2026-11-16 18:10:00',0,0,'normal'),(355,5,'2026-11-13','2026-11-13 08:50:00','2026-11-13 18:10:00',0,0,'normal'),(356,5,'2026-11-12','2026-11-12 08:50:00','2026-11-12 18:10:00',0,0,'normal'),(357,5,'2026-11-11',NULL,NULL,0,0,'leave'),(358,5,'2026-11-10','2026-11-10 09:12:00','2026-11-10 18:05:00',12,0,'late'),(359,5,'2026-11-09','2026-11-09 08:55:00','2026-11-09 17:40:00',0,20,'early'),(360,5,'2026-11-06','2026-11-06 08:50:00','2026-11-06 18:10:00',0,0,'normal'),(361,5,'2026-11-05','2026-11-05 08:50:00','2026-11-05 18:10:00',0,0,'normal'),(362,5,'2026-11-04','2026-11-04 08:50:00','2026-11-04 18:10:00',0,0,'normal'),(363,5,'2026-11-03','2026-11-03 08:50:00','2026-11-03 18:10:00',0,0,'normal'),(364,5,'2026-11-02','2026-11-02 08:50:00','2026-11-02 18:10:00',0,0,'normal'),(365,5,'2026-10-30','2026-10-30 08:55:00','2026-10-30 17:40:00',0,20,'early'),(366,5,'2026-10-29','2026-10-29 09:25:00','2026-10-29 17:30:00',12,20,'late,early'),(367,5,'2026-10-28','2026-10-28 08:50:00','2026-10-28 18:10:00',0,0,'normal'),(368,5,'2026-10-27','2026-10-27 08:50:00','2026-10-27 18:10:00',0,0,'normal'),(369,5,'2026-10-26','2026-10-26 08:50:00','2026-10-26 18:10:00',0,0,'normal'),(370,5,'2026-10-23','2026-10-23 08:50:00','2026-10-23 18:10:00',0,0,'normal'),(371,5,'2026-10-22',NULL,NULL,0,0,'leave'),(372,5,'2026-10-21','2026-10-21 09:12:00','2026-10-21 18:05:00',12,0,'late'),(373,5,'2026-10-20','2026-10-20 08:55:00','2026-10-20 17:40:00',0,20,'early'),(374,5,'2026-10-19','2026-10-19 09:25:00','2026-10-19 17:30:00',12,20,'late,early'),(375,6,'2026-11-17','2026-11-17 08:50:00','2026-11-17 18:10:00',0,0,'normal'),(376,6,'2026-11-16','2026-11-16 08:50:00','2026-11-16 18:10:00',0,0,'normal'),(377,6,'2026-11-13','2026-11-13 08:50:00','2026-11-13 18:10:00',0,0,'normal'),(378,6,'2026-11-12',NULL,NULL,0,0,'leave'),(379,6,'2026-11-11','2026-11-11 09:12:00','2026-11-11 18:05:00',12,0,'late'),(380,6,'2026-11-10','2026-11-10 08:55:00','2026-11-10 17:40:00',0,20,'early'),(381,6,'2026-11-09','2026-11-09 09:25:00','2026-11-09 17:30:00',12,20,'late,early'),(382,6,'2026-11-06','2026-11-06 08:50:00','2026-11-06 18:10:00',0,0,'normal'),(383,6,'2026-11-05','2026-11-05 08:50:00','2026-11-05 18:10:00',0,0,'normal'),(384,6,'2026-11-04','2026-11-04 08:50:00','2026-11-04 18:10:00',0,0,'normal'),(385,6,'2026-11-03','2026-11-03 08:50:00','2026-11-03 18:10:00',0,0,'normal'),(386,6,'2026-11-02',NULL,NULL,0,0,'leave'),(387,6,'2026-10-30','2026-10-30 09:25:00','2026-10-30 17:30:00',12,20,'late,early'),(388,6,'2026-10-29','2026-10-29 08:50:00','2026-10-29 18:10:00',0,0,'normal'),(389,6,'2026-10-28','2026-10-28 08:50:00','2026-10-28 18:10:00',0,0,'normal'),(390,6,'2026-10-27','2026-10-27 08:50:00','2026-10-27 18:10:00',0,0,'normal'),(391,6,'2026-10-26','2026-10-26 08:50:00','2026-10-26 18:10:00',0,0,'normal'),(392,6,'2026-10-23',NULL,NULL,0,0,'leave'),(393,6,'2026-10-22','2026-10-22 09:12:00','2026-10-22 18:05:00',12,0,'late'),(394,6,'2026-10-21','2026-10-21 08:55:00','2026-10-21 17:40:00',0,20,'early'),(395,6,'2026-10-20','2026-10-20 09:25:00','2026-10-20 17:30:00',12,20,'late,early'),(396,6,'2026-10-19','2026-10-19 08:50:00','2026-10-19 18:10:00',0,0,'normal'),(397,15,'2026-11-17','2026-11-17 08:50:00','2026-11-17 18:10:00',0,0,'normal'),(398,15,'2026-11-16','2026-11-16 08:50:00','2026-11-16 18:10:00',0,0,'normal'),(399,15,'2026-11-13',NULL,NULL,0,0,'leave'),(400,15,'2026-11-12','2026-11-12 09:12:00','2026-11-12 18:05:00',12,0,'late'),(401,15,'2026-11-11','2026-11-11 08:55:00','2026-11-11 17:40:00',0,20,'early'),(402,15,'2026-11-10','2026-11-10 09:25:00','2026-11-10 17:30:00',12,20,'late,early'),(403,15,'2026-11-09','2026-11-09 08:50:00','2026-11-09 18:10:00',0,0,'normal'),(404,15,'2026-11-06','2026-11-06 08:50:00','2026-11-06 18:10:00',0,0,'normal'),(405,15,'2026-11-05','2026-11-05 08:50:00','2026-11-05 18:10:00',0,0,'normal'),(406,15,'2026-11-04','2026-11-04 08:50:00','2026-11-04 18:10:00',0,0,'normal'),(407,15,'2026-11-03',NULL,NULL,0,0,'leave'),(408,15,'2026-11-02','2026-11-02 09:12:00','2026-11-02 18:05:00',12,0,'late'),(409,15,'2026-10-30','2026-10-30 08:50:00','2026-10-30 18:10:00',0,0,'normal'),(410,15,'2026-10-29','2026-10-29 08:50:00','2026-10-29 18:10:00',0,0,'normal'),(411,15,'2026-10-28','2026-10-28 08:50:00','2026-10-28 18:10:00',0,0,'normal'),(412,15,'2026-10-27','2026-10-27 08:50:00','2026-10-27 18:10:00',0,0,'normal'),(413,15,'2026-10-26','2026-10-26 08:50:00','2026-10-26 18:10:00',0,0,'normal'),(414,15,'2026-10-23','2026-10-23 09:12:00','2026-10-23 18:05:00',12,0,'late'),(415,15,'2026-10-22','2026-10-22 08:55:00','2026-10-22 17:40:00',0,20,'early'),(416,15,'2026-10-21','2026-10-21 09:25:00','2026-10-21 17:30:00',12,20,'late,early'),(417,15,'2026-10-20','2026-10-20 08:50:00','2026-10-20 18:10:00',0,0,'normal'),(418,15,'2026-10-19','2026-10-19 08:50:00','2026-10-19 18:10:00',0,0,'normal'),(419,16,'2026-11-17','2026-11-17 08:50:00','2026-11-17 18:10:00',0,0,'normal'),(420,16,'2026-11-16','2026-11-16 08:50:00','2026-11-16 18:10:00',0,0,'normal'),(421,16,'2026-11-13','2026-11-13 09:12:00','2026-11-13 18:05:00',12,0,'late'),(422,16,'2026-11-12','2026-11-12 08:55:00','2026-11-12 17:40:00',0,20,'early'),(423,16,'2026-11-11','2026-11-11 09:25:00','2026-11-11 17:30:00',12,20,'late,early'),(424,16,'2026-11-10','2026-11-10 08:50:00','2026-11-10 18:10:00',0,0,'normal'),(425,16,'2026-11-09','2026-11-09 08:50:00','2026-11-09 18:10:00',0,0,'normal'),(426,16,'2026-11-06','2026-11-06 08:50:00','2026-11-06 18:10:00',0,0,'normal'),(427,16,'2026-11-05','2026-11-05 08:50:00','2026-11-05 18:10:00',0,0,'normal'),(428,16,'2026-11-04',NULL,NULL,0,0,'leave'),(429,16,'2026-11-03','2026-11-03 09:12:00','2026-11-03 18:05:00',12,0,'late'),(430,16,'2026-11-02','2026-11-02 08:55:00','2026-11-02 17:40:00',0,20,'early'),(431,16,'2026-10-30','2026-10-30 08:50:00','2026-10-30 18:10:00',0,0,'normal'),(432,16,'2026-10-29','2026-10-29 08:50:00','2026-10-29 18:10:00',0,0,'normal'),(433,16,'2026-10-28','2026-10-28 08:50:00','2026-10-28 18:10:00',0,0,'normal'),(434,16,'2026-10-27','2026-10-27 08:50:00','2026-10-27 18:10:00',0,0,'normal'),(435,16,'2026-10-26','2026-10-26 08:50:00','2026-10-26 18:10:00',0,0,'normal'),(436,16,'2026-10-23','2026-10-23 08:55:00','2026-10-23 17:40:00',0,20,'early'),(437,16,'2026-10-22','2026-10-22 09:25:00','2026-10-22 17:30:00',12,20,'late,early'),(438,16,'2026-10-21','2026-10-21 08:50:00','2026-10-21 18:10:00',0,0,'normal'),(439,16,'2026-10-20','2026-10-20 08:50:00','2026-10-20 18:10:00',0,0,'normal'),(440,16,'2026-10-19','2026-10-19 08:50:00','2026-10-19 18:10:00',0,0,'normal'),(441,17,'2026-11-17','2026-11-17 08:50:00','2026-11-17 18:10:00',0,0,'normal'),(442,17,'2026-11-16','2026-11-16 08:50:00','2026-11-16 18:10:00',0,0,'normal'),(443,17,'2026-11-13','2026-11-13 08:55:00','2026-11-13 17:40:00',0,20,'early'),(444,17,'2026-11-12','2026-11-12 09:25:00','2026-11-12 17:30:00',12,20,'late,early'),(445,17,'2026-11-11','2026-11-11 08:50:00','2026-11-11 18:10:00',0,0,'normal'),(446,17,'2026-11-10','2026-11-10 08:50:00','2026-11-10 18:10:00',0,0,'normal'),(447,17,'2026-11-09','2026-11-09 08:50:00','2026-11-09 18:10:00',0,0,'normal'),(448,17,'2026-11-06','2026-11-06 08:50:00','2026-11-06 18:10:00',0,0,'normal'),(449,17,'2026-11-05',NULL,NULL,0,0,'leave'),(450,17,'2026-11-04','2026-11-04 09:12:00','2026-11-04 18:05:00',12,0,'late'),(451,17,'2026-11-03','2026-11-03 08:55:00','2026-11-03 17:40:00',0,20,'early'),(452,17,'2026-11-02','2026-11-02 09:25:00','2026-11-02 17:30:00',12,20,'late,early'),(453,17,'2026-10-30','2026-10-30 08:50:00','2026-10-30 18:10:00',0,0,'normal'),(454,17,'2026-10-29','2026-10-29 08:50:00','2026-10-29 18:10:00',0,0,'normal'),(455,17,'2026-10-28','2026-10-28 08:50:00','2026-10-28 18:10:00',0,0,'normal'),(456,17,'2026-10-27','2026-10-27 08:50:00','2026-10-27 18:10:00',0,0,'normal'),(457,17,'2026-10-26',NULL,NULL,0,0,'leave'),(458,17,'2026-10-23','2026-10-23 09:25:00','2026-10-23 17:30:00',12,20,'late,early'),(459,17,'2026-10-22','2026-10-22 08:50:00','2026-10-22 18:10:00',0,0,'normal'),(460,17,'2026-10-21','2026-10-21 08:50:00','2026-10-21 18:10:00',0,0,'normal'),(461,17,'2026-10-20','2026-10-20 08:50:00','2026-10-20 18:10:00',0,0,'normal'),(462,17,'2026-10-19','2026-10-19 08:50:00','2026-10-19 18:10:00',0,0,'normal'),(463,18,'2026-11-17','2026-11-17 08:50:00','2026-11-17 18:10:00',0,0,'normal'),(464,18,'2026-11-16',NULL,NULL,0,0,'leave'),(465,18,'2026-11-13','2026-11-13 09:25:00','2026-11-13 17:30:00',12,20,'late,early'),(466,18,'2026-11-12','2026-11-12 08:50:00','2026-11-12 18:10:00',0,0,'normal'),(467,18,'2026-11-11','2026-11-11 08:50:00','2026-11-11 18:10:00',0,0,'normal'),(468,18,'2026-11-10','2026-11-10 08:50:00','2026-11-10 18:10:00',0,0,'normal'),(469,18,'2026-11-09','2026-11-09 08:50:00','2026-11-09 18:10:00',0,0,'normal'),(470,18,'2026-11-06',NULL,NULL,0,0,'leave'),(471,18,'2026-11-05','2026-11-05 09:12:00','2026-11-05 18:05:00',12,0,'late'),(472,18,'2026-11-04','2026-11-04 08:55:00','2026-11-04 17:40:00',0,20,'early'),(473,18,'2026-11-03','2026-11-03 09:25:00','2026-11-03 17:30:00',12,20,'late,early'),(474,18,'2026-11-02','2026-11-02 08:50:00','2026-11-02 18:10:00',0,0,'normal'),(475,18,'2026-10-30','2026-10-30 08:50:00','2026-10-30 18:10:00',0,0,'normal'),(476,18,'2026-10-29','2026-10-29 08:50:00','2026-10-29 18:10:00',0,0,'normal'),(477,18,'2026-10-28','2026-10-28 08:50:00','2026-10-28 18:10:00',0,0,'normal'),(478,18,'2026-10-27',NULL,NULL,0,0,'leave'),(479,18,'2026-10-26','2026-10-26 09:12:00','2026-10-26 18:05:00',12,0,'late'),(480,18,'2026-10-23','2026-10-23 08:50:00','2026-10-23 18:10:00',0,0,'normal'),(481,18,'2026-10-22','2026-10-22 08:50:00','2026-10-22 18:10:00',0,0,'normal'),(482,18,'2026-10-21','2026-10-21 08:50:00','2026-10-21 18:10:00',0,0,'normal'),(483,18,'2026-10-20','2026-10-20 08:50:00','2026-10-20 18:10:00',0,0,'normal'),(484,18,'2026-10-19','2026-10-19 08:50:00','2026-10-19 18:10:00',0,0,'normal'),(485,19,'2026-11-17',NULL,NULL,0,0,'leave'),(486,19,'2026-11-16','2026-11-16 09:12:00','2026-11-16 18:05:00',12,0,'late'),(487,19,'2026-11-13','2026-11-13 08:50:00','2026-11-13 18:10:00',0,0,'normal'),(488,19,'2026-11-12','2026-11-12 08:50:00','2026-11-12 18:10:00',0,0,'normal'),(489,19,'2026-11-11','2026-11-11 08:50:00','2026-11-11 18:10:00',0,0,'normal'),(490,19,'2026-11-10','2026-11-10 08:50:00','2026-11-10 18:10:00',0,0,'normal'),(491,19,'2026-11-09','2026-11-09 08:50:00','2026-11-09 18:10:00',0,0,'normal'),(492,19,'2026-11-06','2026-11-06 09:12:00','2026-11-06 18:05:00',12,0,'late'),(493,19,'2026-11-05','2026-11-05 08:55:00','2026-11-05 17:40:00',0,20,'early'),(494,19,'2026-11-04','2026-11-04 09:25:00','2026-11-04 17:30:00',12,20,'late,early'),(495,19,'2026-11-03','2026-11-03 08:50:00','2026-11-03 18:10:00',0,0,'normal'),(496,19,'2026-11-02','2026-11-02 08:50:00','2026-11-02 18:10:00',0,0,'normal'),(497,19,'2026-10-30','2026-10-30 08:50:00','2026-10-30 18:10:00',0,0,'normal'),(498,19,'2026-10-29','2026-10-29 08:50:00','2026-10-29 18:10:00',0,0,'normal'),(499,19,'2026-10-28',NULL,NULL,0,0,'leave'),(500,19,'2026-10-27','2026-10-27 09:12:00','2026-10-27 18:05:00',12,0,'late'),(501,19,'2026-10-26','2026-10-26 08:55:00','2026-10-26 17:40:00',0,20,'early'),(502,19,'2026-10-23','2026-10-23 08:50:00','2026-10-23 18:10:00',0,0,'normal'),(503,19,'2026-10-22','2026-10-22 08:50:00','2026-10-22 18:10:00',0,0,'normal'),(504,19,'2026-10-21','2026-10-21 08:50:00','2026-10-21 18:10:00',0,0,'normal'),(505,19,'2026-10-20','2026-10-20 08:50:00','2026-10-20 18:10:00',0,0,'normal'),(506,19,'2026-10-19','2026-10-19 08:50:00','2026-10-19 18:10:00',0,0,'normal'),(507,20,'2026-11-17','2026-11-17 09:12:00','2026-11-17 18:05:00',12,0,'late'),(508,20,'2026-11-16','2026-11-16 08:55:00','2026-11-16 17:40:00',0,20,'early'),(509,20,'2026-11-13','2026-11-13 08:50:00','2026-11-13 18:10:00',0,0,'normal'),(510,20,'2026-11-12','2026-11-12 08:50:00','2026-11-12 18:10:00',0,0,'normal'),(511,20,'2026-11-11','2026-11-11 08:50:00','2026-11-11 18:10:00',0,0,'normal'),(512,20,'2026-11-10','2026-11-10 08:50:00','2026-11-10 18:10:00',0,0,'normal'),(513,20,'2026-11-09','2026-11-09 08:50:00','2026-11-09 18:10:00',0,0,'normal'),(514,20,'2026-11-06','2026-11-06 08:55:00','2026-11-06 17:40:00',0,20,'early'),(515,20,'2026-11-05','2026-11-05 09:25:00','2026-11-05 17:30:00',12,20,'late,early'),(516,20,'2026-11-04','2026-11-04 08:50:00','2026-11-04 18:10:00',0,0,'normal'),(517,20,'2026-11-03','2026-11-03 08:50:00','2026-11-03 18:10:00',0,0,'normal'),(518,20,'2026-11-02','2026-11-02 08:50:00','2026-11-02 18:10:00',0,0,'normal'),(519,20,'2026-10-30','2026-10-30 08:50:00','2026-10-30 18:10:00',0,0,'normal'),(520,20,'2026-10-29',NULL,NULL,0,0,'leave'),(521,20,'2026-10-28','2026-10-28 09:12:00','2026-10-28 18:05:00',12,0,'late'),(522,20,'2026-10-27','2026-10-27 08:55:00','2026-10-27 17:40:00',0,20,'early'),(523,20,'2026-10-26','2026-10-26 09:25:00','2026-10-26 17:30:00',12,20,'late,early'),(524,20,'2026-10-23','2026-10-23 08:50:00','2026-10-23 18:10:00',0,0,'normal'),(525,20,'2026-10-22','2026-10-22 08:50:00','2026-10-22 18:10:00',0,0,'normal'),(526,20,'2026-10-21','2026-10-21 08:50:00','2026-10-21 18:10:00',0,0,'normal'),(527,20,'2026-10-20','2026-10-20 08:50:00','2026-10-20 18:10:00',0,0,'normal'),(528,20,'2026-10-19',NULL,NULL,0,0,'leave'),(529,21,'2026-11-17','2026-11-17 08:55:00','2026-11-17 17:40:00',0,20,'early'),(530,21,'2026-11-16','2026-11-16 09:25:00','2026-11-16 17:30:00',12,20,'late,early'),(531,21,'2026-11-13','2026-11-13 08:50:00','2026-11-13 18:10:00',0,0,'normal'),(532,21,'2026-11-12','2026-11-12 08:50:00','2026-11-12 18:10:00',0,0,'normal'),(533,21,'2026-11-11','2026-11-11 08:50:00','2026-11-11 18:10:00',0,0,'normal'),(534,21,'2026-11-10','2026-11-10 08:50:00','2026-11-10 18:10:00',0,0,'normal'),(535,21,'2026-11-09',NULL,NULL,0,0,'leave'),(536,21,'2026-11-06','2026-11-06 09:25:00','2026-11-06 17:30:00',12,20,'late,early'),(537,21,'2026-11-05','2026-11-05 08:50:00','2026-11-05 18:10:00',0,0,'normal'),(538,21,'2026-11-04','2026-11-04 08:50:00','2026-11-04 18:10:00',0,0,'normal'),(539,21,'2026-11-03','2026-11-03 08:50:00','2026-11-03 18:10:00',0,0,'normal'),(540,21,'2026-11-02','2026-11-02 08:50:00','2026-11-02 18:10:00',0,0,'normal'),(541,21,'2026-10-30',NULL,NULL,0,0,'leave'),(542,21,'2026-10-29','2026-10-29 09:12:00','2026-10-29 18:05:00',12,0,'late'),(543,21,'2026-10-28','2026-10-28 08:55:00','2026-10-28 17:40:00',0,20,'early'),(544,21,'2026-10-27','2026-10-27 09:25:00','2026-10-27 17:30:00',12,20,'late,early'),(545,21,'2026-10-26','2026-10-26 08:50:00','2026-10-26 18:10:00',0,0,'normal'),(546,21,'2026-10-23','2026-10-23 08:50:00','2026-10-23 18:10:00',0,0,'normal'),(547,21,'2026-10-22','2026-10-22 08:50:00','2026-10-22 18:10:00',0,0,'normal'),(548,21,'2026-10-21','2026-10-21 08:50:00','2026-10-21 18:10:00',0,0,'normal'),(549,21,'2026-10-20',NULL,NULL,0,0,'leave'),(550,21,'2026-10-19','2026-10-19 09:12:00','2026-10-19 18:05:00',12,0,'late'),(551,22,'2026-11-17','2026-11-17 09:25:00','2026-11-17 17:30:00',12,20,'late,early'),(552,22,'2026-11-16','2026-11-16 08:50:00','2026-11-16 18:10:00',0,0,'normal'),(553,22,'2026-11-13','2026-11-13 08:50:00','2026-11-13 18:10:00',0,0,'normal'),(554,22,'2026-11-12','2026-11-12 08:50:00','2026-11-12 18:10:00',0,0,'normal'),(555,22,'2026-11-11','2026-11-11 08:50:00','2026-11-11 18:10:00',0,0,'normal'),(556,22,'2026-11-10',NULL,NULL,0,0,'leave'),(557,22,'2026-11-09','2026-11-09 09:12:00','2026-11-09 18:05:00',12,0,'late'),(558,22,'2026-11-06','2026-11-06 08:50:00','2026-11-06 18:10:00',0,0,'normal'),(559,22,'2026-11-05','2026-11-05 08:50:00','2026-11-05 18:10:00',0,0,'normal'),(560,22,'2026-11-04','2026-11-04 08:50:00','2026-11-04 18:10:00',0,0,'normal'),(561,22,'2026-11-03','2026-11-03 08:50:00','2026-11-03 18:10:00',0,0,'normal'),(562,22,'2026-11-02','2026-11-02 08:50:00','2026-11-02 18:10:00',0,0,'normal'),(563,22,'2026-10-30','2026-10-30 09:12:00','2026-10-30 18:05:00',12,0,'late'),(564,22,'2026-10-29','2026-10-29 08:55:00','2026-10-29 17:40:00',0,20,'early'),(565,22,'2026-10-28','2026-10-28 09:25:00','2026-10-28 17:30:00',12,20,'late,early'),(566,22,'2026-10-27','2026-10-27 08:50:00','2026-10-27 18:10:00',0,0,'normal'),(567,22,'2026-10-26','2026-10-26 08:50:00','2026-10-26 18:10:00',0,0,'normal'),(568,22,'2026-10-23','2026-10-23 08:50:00','2026-10-23 18:10:00',0,0,'normal'),(569,22,'2026-10-22','2026-10-22 08:50:00','2026-10-22 18:10:00',0,0,'normal'),(570,22,'2026-10-21',NULL,NULL,0,0,'leave'),(571,22,'2026-10-20','2026-10-20 09:12:00','2026-10-20 18:05:00',12,0,'late'),(572,22,'2026-10-19','2026-10-19 08:55:00','2026-10-19 17:40:00',0,20,'early');
/*!40000 ALTER TABLE `attendance_records` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `chat_messages`
--

DROP TABLE IF EXISTS `chat_messages`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `chat_messages` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `sender_id` int(11) NOT NULL COMMENT '发送人',
  `receiver_id` int(11) NOT NULL COMMENT '接收人',
  `content` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '消息内容',
  `is_read` tinyint(1) NOT NULL COMMENT '已读标记',
  `created_at` datetime NOT NULL COMMENT '发送时间',
  PRIMARY KEY (`id`),
  KEY `ix_chat_pair_time` (`sender_id`,`receiver_id`,`created_at`),
  KEY `ix_chat_receiver_read` (`receiver_id`,`is_read`),
  CONSTRAINT `chat_messages_ibfk_1` FOREIGN KEY (`receiver_id`) REFERENCES `users` (`id`),
  CONSTRAINT `chat_messages_ibfk_2` FOREIGN KEY (`sender_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=13 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `chat_messages`
--

LOCK TABLES `chat_messages` WRITE;
/*!40000 ALTER TABLE `chat_messages` DISABLE KEYS */;
INSERT INTO `chat_messages` VALUES (1,1,2,'测试消息 1-1：你好，这是一条用于演示的站内消息。',1,'2026-11-18 09:00:00'),(2,1,2,'测试消息 1-2：你好，这是一条用于演示的站内消息。',1,'2026-11-18 09:05:00'),(3,1,2,'测试消息 1-3：你好，这是一条用于演示的站内消息。',0,'2026-11-18 09:10:00'),(4,1,2,'测试消息 1-4：你好，这是一条用于演示的站内消息。',0,'2026-11-18 09:15:00'),(5,2,3,'测试消息 2-1：你好，这是一条用于演示的站内消息。',1,'2026-11-18 09:00:00'),(6,2,3,'测试消息 2-2：你好，这是一条用于演示的站内消息。',1,'2026-11-18 09:05:00'),(7,2,3,'测试消息 2-3：你好，这是一条用于演示的站内消息。',0,'2026-11-18 09:10:00'),(8,2,3,'测试消息 2-4：你好，这是一条用于演示的站内消息。',0,'2026-11-18 09:15:00'),(9,1,3,'测试消息 3-1：你好，这是一条用于演示的站内消息。',1,'2026-11-18 09:00:00'),(10,1,3,'测试消息 3-2：你好，这是一条用于演示的站内消息。',1,'2026-11-18 09:05:00'),(11,1,3,'测试消息 3-3：你好，这是一条用于演示的站内消息。',0,'2026-11-18 09:10:00'),(12,1,3,'测试消息 3-4：你好，这是一条用于演示的站内消息。',0,'2026-11-18 09:15:00');
/*!40000 ALTER TABLE `chat_messages` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `conversation_reads`
--

DROP TABLE IF EXISTS `conversation_reads`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `conversation_reads` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL COMMENT '本端用户',
  `peer_id` int(11) NOT NULL COMMENT '对方用户',
  `last_read_message_id` int(11) NOT NULL COMMENT '已读位点',
  `updated_at` datetime NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_conversation_read_user_peer` (`user_id`,`peer_id`),
  KEY `peer_id` (`peer_id`),
  CONSTRAINT `conversation_reads_ibfk_1` FOREIGN KEY (`peer_id`) REFERENCES `users` (`id`),
  CONSTRAINT `conversation_reads_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `conversation_reads`
--

LOCK TABLES `conversation_reads` WRITE;
/*!40000 ALTER TABLE `conversation_reads` DISABLE KEYS */;
INSERT INTO `conversation_reads` VALUES (1,2,1,0,'2026-11-18 02:04:06'),(2,3,2,0,'2026-11-18 02:04:06'),(3,3,1,0,'2026-11-18 02:04:06');
/*!40000 ALTER TABLE `conversation_reads` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `departments`
--

DROP TABLE IF EXISTS `departments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `departments` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '部门名称',
  `parent_id` int(11) DEFAULT NULL COMMENT '上级部门，空为根',
  `leader_id` int(11) DEFAULT NULL COMMENT '部门负责人',
  `sort_order` int(11) NOT NULL COMMENT '排序号',
  `is_active` tinyint(1) NOT NULL COMMENT '停用=软删',
  PRIMARY KEY (`id`),
  KEY `parent_id` (`parent_id`),
  CONSTRAINT `departments_ibfk_1` FOREIGN KEY (`parent_id`) REFERENCES `departments` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `departments`
--

LOCK TABLES `departments` WRITE;
/*!40000 ALTER TABLE `departments` DISABLE KEYS */;
INSERT INTO `departments` VALUES (1,'生产部',NULL,2,0,1),(2,'仓储部',NULL,3,0,1),(3,'综合部',NULL,NULL,0,1),(8,'一车间',1,NULL,1,1),(9,'二车间',1,NULL,1,1),(10,'质检组',1,NULL,1,1),(11,'原料组',2,NULL,1,1);
/*!40000 ALTER TABLE `departments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `factory_files`
--

DROP TABLE IF EXISTS `factory_files`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `factory_files` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '显示名',
  `original_filename` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '原始文件名',
  `stored_filename` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '磁盘存储名（uuid）',
  `file_ext` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '扩展名',
  `size_bytes` int(11) NOT NULL COMMENT '文件大小(字节)',
  `category_id` int(11) DEFAULT NULL COMMENT '分类，可空',
  `visibility_type` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL,
  `uploaded_by` int(11) NOT NULL COMMENT '上传人',
  `created_at` datetime NOT NULL COMMENT '上传时间',
  `is_active` tinyint(1) NOT NULL COMMENT '停用=软删',
  PRIMARY KEY (`id`),
  KEY `category_id` (`category_id`),
  KEY `uploaded_by` (`uploaded_by`),
  CONSTRAINT `factory_files_ibfk_1` FOREIGN KEY (`category_id`) REFERENCES `file_categories` (`id`),
  CONSTRAINT `factory_files_ibfk_2` FOREIGN KEY (`uploaded_by`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `factory_files`
--

LOCK TABLES `factory_files` WRITE;
/*!40000 ALTER TABLE `factory_files` DISABLE KEYS */;
INSERT INTO `factory_files` VALUES (1,'产品图纸A','test_1.pdf','test_1.pdf','.pdf',102400,1,'all',1,'2026-11-18 11:00:00',1),(2,'作业指导书','test_2.docx','test_2.docx','.docx',204800,1,'all',1,'2026-11-17 11:00:00',1),(3,'车间照片','test_3.png','test_3.png','.png',307200,1,'all',1,'2026-11-16 11:00:00',1),(4,'检验标准','test_4.pdf','test_4.pdf','.pdf',409600,1,'all',1,'2026-11-15 11:00:00',1);
/*!40000 ALTER TABLE `factory_files` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `file_categories`
--

DROP TABLE IF EXISTS `file_categories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `file_categories` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '分类名称',
  `parent_id` int(11) DEFAULT NULL COMMENT '上级分类',
  `is_active` tinyint(1) NOT NULL COMMENT '停用=软删',
  PRIMARY KEY (`id`),
  KEY `parent_id` (`parent_id`),
  CONSTRAINT `file_categories_ibfk_1` FOREIGN KEY (`parent_id`) REFERENCES `file_categories` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `file_categories`
--

LOCK TABLES `file_categories` WRITE;
/*!40000 ALTER TABLE `file_categories` DISABLE KEYS */;
INSERT INTO `file_categories` VALUES (1,'技术文档',NULL,1);
/*!40000 ALTER TABLE `file_categories` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `file_department_visibility`
--

DROP TABLE IF EXISTS `file_department_visibility`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `file_department_visibility` (
  `file_id` int(11) NOT NULL,
  `department_id` int(11) NOT NULL,
  PRIMARY KEY (`file_id`,`department_id`),
  KEY `department_id` (`department_id`),
  CONSTRAINT `file_department_visibility_ibfk_1` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`),
  CONSTRAINT `file_department_visibility_ibfk_2` FOREIGN KEY (`file_id`) REFERENCES `factory_files` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `file_department_visibility`
--

LOCK TABLES `file_department_visibility` WRITE;
/*!40000 ALTER TABLE `file_department_visibility` DISABLE KEYS */;
/*!40000 ALTER TABLE `file_department_visibility` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `file_role_visibility`
--

DROP TABLE IF EXISTS `file_role_visibility`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `file_role_visibility` (
  `file_id` int(11) NOT NULL,
  `role_id` int(11) NOT NULL,
  PRIMARY KEY (`file_id`,`role_id`),
  KEY `role_id` (`role_id`),
  CONSTRAINT `file_role_visibility_ibfk_1` FOREIGN KEY (`file_id`) REFERENCES `factory_files` (`id`),
  CONSTRAINT `file_role_visibility_ibfk_2` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `file_role_visibility`
--

LOCK TABLES `file_role_visibility` WRITE;
/*!40000 ALTER TABLE `file_role_visibility` DISABLE KEYS */;
/*!40000 ALTER TABLE `file_role_visibility` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `inventories`
--

DROP TABLE IF EXISTS `inventories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `inventories` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `warehouse_id` int(11) NOT NULL COMMENT '仓库',
  `material_id` int(11) NOT NULL COMMENT '物料',
  `quantity` int(11) NOT NULL COMMENT '当前数量 >=0',
  `warn_threshold` int(11) NOT NULL COMMENT '预警阈值',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_inventory_wh_mat` (`warehouse_id`,`material_id`),
  KEY `material_id` (`material_id`),
  CONSTRAINT `inventories_ibfk_1` FOREIGN KEY (`material_id`) REFERENCES `materials` (`id`),
  CONSTRAINT `inventories_ibfk_2` FOREIGN KEY (`warehouse_id`) REFERENCES `warehouses` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=36 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `inventories`
--

LOCK TABLES `inventories` WRITE;
/*!40000 ALTER TABLE `inventories` DISABLE KEYS */;
INSERT INTO `inventories` VALUES (1,1,1,65,10),(19,1,2,70,10),(20,1,3,75,10),(21,1,10,80,10),(22,1,11,85,10),(23,1,12,90,10),(24,2,1,95,10),(25,2,2,100,10),(26,2,3,105,10),(27,2,10,110,10),(28,2,11,115,10),(29,2,12,120,10),(30,4,1,125,10),(31,4,2,130,10),(32,4,3,135,10),(33,4,10,140,10),(34,4,11,145,10),(35,4,12,150,10);
/*!40000 ALTER TABLE `inventories` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `leave_requests`
--

DROP TABLE IF EXISTS `leave_requests`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `leave_requests` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `applicant_id` int(11) NOT NULL COMMENT '申请人',
  `department_id` int(11) DEFAULT NULL COMMENT '申请时部门',
  `leave_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '请假类型',
  `start_at` datetime NOT NULL COMMENT '开始时间',
  `end_at` datetime NOT NULL COMMENT '结束时间',
  `days` float NOT NULL COMMENT '天数',
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '事由',
  `status` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '状态',
  `approver_id` int(11) DEFAULT NULL COMMENT '审批人',
  `approved_at` datetime DEFAULT NULL COMMENT '审批时间',
  `approve_comment` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '审批意见',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `approver_id` (`approver_id`),
  KEY `ix_leave_dept_status` (`department_id`,`status`),
  KEY `ix_leave_applicant_created` (`applicant_id`,`created_at`),
  CONSTRAINT `leave_requests_ibfk_1` FOREIGN KEY (`applicant_id`) REFERENCES `users` (`id`),
  CONSTRAINT `leave_requests_ibfk_2` FOREIGN KEY (`approver_id`) REFERENCES `users` (`id`),
  CONSTRAINT `leave_requests_ibfk_3` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `leave_requests`
--

LOCK TABLES `leave_requests` WRITE;
/*!40000 ALTER TABLE `leave_requests` DISABLE KEYS */;
INSERT INTO `leave_requests` VALUES (6,2,1,'事假','2026-11-17 09:00:00','2026-11-17 18:00:00',1,'家中有事','approved',2,'2026-11-17 10:00:00','同意','2026-11-15 10:00:00'),(7,3,2,'病假','2026-11-16 09:00:00','2026-11-16 18:00:00',1,'身体不适就医','pending',NULL,NULL,'','2026-11-14 10:00:00'),(8,4,1,'年假','2026-11-15 09:00:00','2026-11-15 18:00:00',1,'年假休息','approved',2,'2026-11-15 10:00:00','同意','2026-11-13 10:00:00'),(9,5,1,'调休','2026-11-14 09:00:00','2026-11-14 18:00:00',1,'加班调休申请','rejected',2,'2026-11-14 10:00:00','不同意','2026-11-12 10:00:00'),(10,6,3,'事假','2026-11-13 09:00:00','2026-11-13 18:00:00',1,'个人事务','pending',NULL,NULL,'','2026-11-11 10:00:00');
/*!40000 ALTER TABLE `leave_requests` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `material_categories`
--

DROP TABLE IF EXISTS `material_categories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `material_categories` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '分类名称',
  `parent_id` int(11) DEFAULT NULL COMMENT '上级分类',
  `is_active` tinyint(1) NOT NULL COMMENT '停用=软删',
  PRIMARY KEY (`id`),
  KEY `parent_id` (`parent_id`),
  CONSTRAINT `material_categories_ibfk_1` FOREIGN KEY (`parent_id`) REFERENCES `material_categories` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `material_categories`
--

LOCK TABLES `material_categories` WRITE;
/*!40000 ALTER TABLE `material_categories` DISABLE KEYS */;
INSERT INTO `material_categories` VALUES (1,'五金件',NULL,1),(2,'包装耗材',NULL,1),(4,'电子元件',NULL,1);
/*!40000 ALTER TABLE `material_categories` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `materials`
--

DROP TABLE IF EXISTS `materials`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `materials` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `code` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '物料编码',
  `name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '物料名称',
  `spec` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '规格',
  `unit` varchar(16) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '单位',
  `category_id` int(11) DEFAULT NULL COMMENT '分类，可空',
  `is_active` tinyint(1) NOT NULL COMMENT '停用=软删',
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  KEY `category_id` (`category_id`),
  CONSTRAINT `materials_ibfk_1` FOREIGN KEY (`category_id`) REFERENCES `material_categories` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=16 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `materials`
--

LOCK TABLES `materials` WRITE;
/*!40000 ALTER TABLE `materials` DISABLE KEYS */;
INSERT INTO `materials` VALUES (1,'M0001','内六角螺丝','M8×30','盒',1,1),(2,'M0002','轴承','6204','个',1,1),(3,'M0003','纸箱','400×300×200','个',2,1),(10,'M0004','电阻','10KΩ','个',4,1),(11,'M0005','电容','100μF','个',4,1),(12,'M0006','PCB板','A型','块',4,1),(13,'M0007','螺丝刀','十字','把',1,1),(14,'M0008','胶带','宽48mm','卷',2,1),(15,'M0009','泡沫垫','A4','片',2,1);
/*!40000 ALTER TABLE `materials` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `notifications`
--

DROP TABLE IF EXISTS `notifications`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `notifications` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `receiver_id` int(11) NOT NULL COMMENT '接收人',
  `notif_type` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '消息类型',
  `title` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '标题',
  `content` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '内容',
  `material_id` int(11) DEFAULT NULL COMMENT '关联物料',
  `warehouse_id` int(11) DEFAULT NULL COMMENT '关联仓库',
  `link_url` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '跳转链接',
  `is_read` tinyint(1) NOT NULL COMMENT '是否已读',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `material_id` (`material_id`),
  KEY `warehouse_id` (`warehouse_id`),
  KEY `ix_notif_receiver_read` (`receiver_id`,`is_read`,`created_at`),
  CONSTRAINT `notifications_ibfk_1` FOREIGN KEY (`material_id`) REFERENCES `materials` (`id`),
  CONSTRAINT `notifications_ibfk_2` FOREIGN KEY (`receiver_id`) REFERENCES `users` (`id`),
  CONSTRAINT `notifications_ibfk_3` FOREIGN KEY (`warehouse_id`) REFERENCES `warehouses` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `notifications`
--

LOCK TABLES `notifications` WRITE;
/*!40000 ALTER TABLE `notifications` DISABLE KEYS */;
INSERT INTO `notifications` VALUES (1,3,'stock_warning','库存预警-测试-0','物料库存低于预警阈值，请及时补货（测试数据）',NULL,NULL,'',0,'2026-11-18 08:00:00'),(2,3,'stock_warning','库存预警-测试-1','物料库存低于预警阈值，请及时补货（测试数据）',NULL,NULL,'',1,'2026-11-17 08:00:00');
/*!40000 ALTER TABLE `notifications` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `operation_logs`
--

DROP TABLE IF EXISTS `operation_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `operation_logs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `operator_id` int(11) DEFAULT NULL COMMENT '操作人，可空',
  `module` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '模块',
  `action` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '动作类型',
  `target_type` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '多态目标类型',
  `target_id` int(11) DEFAULT NULL COMMENT '多态目标ID',
  `summary` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '摘要',
  `ip` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '操作IP',
  `created_at` datetime NOT NULL COMMENT '操作时间',
  PRIMARY KEY (`id`),
  KEY `ix_oplog_module_created` (`module`,`created_at`),
  KEY `ix_oplog_operator_created` (`operator_id`,`created_at`),
  KEY `ix_oplog_target` (`target_type`,`target_id`,`created_at`),
  CONSTRAINT `operation_logs_ibfk_1` FOREIGN KEY (`operator_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `operation_logs`
--

LOCK TABLES `operation_logs` WRITE;
/*!40000 ALTER TABLE `operation_logs` DISABLE KEYS */;
INSERT INTO `operation_logs` VALUES (1,1,'hr','create','test',1,'测试操作日志 1：系统演示数据','127.0.0.1','2026-11-18 12:00:00'),(2,1,'warehouse','create','test',2,'测试操作日志 2：系统演示数据','127.0.0.1','2026-11-17 12:01:00'),(3,1,'production','create','test',3,'测试操作日志 3：系统演示数据','127.0.0.1','2026-11-16 12:02:00'),(4,1,'attendance','create','test',4,'测试操作日志 4：系统演示数据','127.0.0.1','2026-11-15 12:03:00'),(5,1,'files','create','test',5,'测试操作日志 5：系统演示数据','127.0.0.1','2026-11-14 12:04:00'),(6,1,'hr','create','test',6,'测试操作日志 6：系统演示数据','127.0.0.1','2026-11-18 12:05:00'),(7,1,'warehouse','create','test',7,'测试操作日志 7：系统演示数据','127.0.0.1','2026-11-17 12:06:00'),(8,1,'production','create','test',8,'测试操作日志 8：系统演示数据','127.0.0.1','2026-11-16 12:07:00'),(9,1,'attendance','create','test',9,'测试操作日志 9：系统演示数据','127.0.0.1','2026-11-15 12:08:00'),(10,1,'files','create','test',10,'测试操作日志 10：系统演示数据','127.0.0.1','2026-11-14 12:09:00'),(11,1,'hr','create','test',11,'测试操作日志 11：系统演示数据','127.0.0.1','2026-11-18 12:10:00'),(12,1,'warehouse','create','test',12,'测试操作日志 12：系统演示数据','127.0.0.1','2026-11-17 12:11:00'),(13,1,'production','create','test',13,'测试操作日志 13：系统演示数据','127.0.0.1','2026-11-16 12:12:00'),(14,1,'attendance','create','test',14,'测试操作日志 14：系统演示数据','127.0.0.1','2026-11-15 12:13:00'),(15,1,'files','create','test',15,'测试操作日志 15：系统演示数据','127.0.0.1','2026-11-14 12:14:00'),(16,1,'auth','login','user',1,'系统管理员 登录成功','127.0.0.1','2026-11-18 02:04:33'),(17,1,'auth','login','user',1,'系统管理员 登录成功','127.0.0.1','2026-11-18 02:04:44');
/*!40000 ALTER TABLE `operation_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `permissions`
--

DROP TABLE IF EXISTS `permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `permissions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `code` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '如 hr.manage',
  `name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '中文名',
  `module` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '所属模块分组',
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=22 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `permissions`
--

LOCK TABLES `permissions` WRITE;
/*!40000 ALTER TABLE `permissions` DISABLE KEYS */;
INSERT INTO `permissions` VALUES (1,'hr.view','员工查看','人员管理'),(2,'hr.manage','员工管理','人员管理'),(3,'dept.manage','部门管理','部门管理'),(4,'rbac.manage','角色权限管理','角色权限'),(5,'attendance.clock','考勤打卡','考勤管理'),(6,'attendance.view','考勤查看','考勤管理'),(7,'attendance.view_all','考勤查看全部','考勤管理'),(8,'attendance.leave.apply','请假申请','考勤管理'),(9,'attendance.leave.approve','请假审批','考勤管理'),(10,'attendance.summary.view','部门考勤汇总','考勤管理'),(11,'production.view','工单查看','生产管理'),(12,'production.manage','工单管理','生产管理'),(13,'production.issue','工单领料','生产管理'),(14,'material.manage','物料管理','物料管理'),(15,'warehouse.view','库存查看','仓库管理'),(16,'warehouse.manage','出入库管理','仓库管理'),(17,'warehouse.ledger.view','库存流水查询','仓库管理'),(18,'files.view','文件查看','文件管理'),(19,'files.manage','文件管理','文件管理'),(20,'system.log.view','操作日志查看','系统管理'),(21,'system.export','数据导出','系统管理');
/*!40000 ALTER TABLE `permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `role_permissions`
--

DROP TABLE IF EXISTS `role_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `role_permissions` (
  `role_id` int(11) NOT NULL,
  `permission_id` int(11) NOT NULL,
  PRIMARY KEY (`role_id`,`permission_id`),
  KEY `permission_id` (`permission_id`),
  CONSTRAINT `role_permissions_ibfk_1` FOREIGN KEY (`permission_id`) REFERENCES `permissions` (`id`),
  CONSTRAINT `role_permissions_ibfk_2` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `role_permissions`
--

LOCK TABLES `role_permissions` WRITE;
/*!40000 ALTER TABLE `role_permissions` DISABLE KEYS */;
INSERT INTO `role_permissions` VALUES (1,1),(2,1),(1,2),(1,3),(1,4),(1,5),(5,5),(1,6),(2,6),(5,6),(1,7),(2,7),(1,8),(2,8),(3,8),(4,8),(5,8),(6,8),(1,9),(2,9),(1,10),(2,10),(1,11),(2,11),(4,11),(1,12),(2,12),(4,12),(1,13),(3,13),(4,13),(1,14),(3,14),(4,14),(1,15),(3,15),(4,15),(1,16),(3,16),(1,17),(3,17),(1,18),(2,18),(3,18),(4,18),(5,18),(6,18),(1,19),(6,19),(1,20),(1,21),(2,21);
/*!40000 ALTER TABLE `role_permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `roles`
--

DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `roles` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `code` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '编码：superadmin/leader/keeper/producer/staff/archivist',
  `name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '中文名称',
  `is_builtin` tinyint(1) NOT NULL COMMENT '内置角色不可删',
  `remark` varchar(200) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '备注',
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `roles`
--

LOCK TABLES `roles` WRITE;
/*!40000 ALTER TABLE `roles` DISABLE KEYS */;
INSERT INTO `roles` VALUES (1,'superadmin','超级管理员',1,'内置角色：全权限（代码硬编码放行）'),(2,'leader','部门主管',1,'内置角色：本部门人员/考勤、工单调度、请假审批、导出'),(3,'keeper','仓管员',1,'内置角色：出入库/库存/物料/流水/领料'),(4,'producer','生产管理员',1,'内置角色：工单创建与流转、领料'),(5,'staff','普通员工',1,'内置角色：打卡/查考勤/看文件/请假'),(6,'archivist','档案管理员',1,'内置角色：文件上传/分类/可见范围');
/*!40000 ALTER TABLE `roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `stock_documents`
--

DROP TABLE IF EXISTS `stock_documents`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `stock_documents` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `doc_no` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '单据号 IN/OUT 前缀',
  `doc_type` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'in=入库 out=出库',
  `warehouse_id` int(11) NOT NULL COMMENT '仓库',
  `material_id` int(11) NOT NULL COMMENT '物料（P0 单物料/单）',
  `quantity` int(11) NOT NULL COMMENT '数量 >0',
  `handler_id` int(11) NOT NULL COMMENT '经手人',
  `related_order_id` int(11) DEFAULT NULL COMMENT '关联工单，可空（P1 领料用）',
  `remark` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '备注',
  `created_by` int(11) NOT NULL COMMENT '创建人',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `doc_no` (`doc_no`),
  KEY `created_by` (`created_by`),
  KEY `handler_id` (`handler_id`),
  KEY `material_id` (`material_id`),
  KEY `related_order_id` (`related_order_id`),
  KEY `warehouse_id` (`warehouse_id`),
  CONSTRAINT `stock_documents_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`),
  CONSTRAINT `stock_documents_ibfk_2` FOREIGN KEY (`handler_id`) REFERENCES `users` (`id`),
  CONSTRAINT `stock_documents_ibfk_3` FOREIGN KEY (`material_id`) REFERENCES `materials` (`id`),
  CONSTRAINT `stock_documents_ibfk_4` FOREIGN KEY (`related_order_id`) REFERENCES `work_orders` (`id`),
  CONSTRAINT `stock_documents_ibfk_5` FOREIGN KEY (`warehouse_id`) REFERENCES `warehouses` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=72 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `stock_documents`
--

LOCK TABLES `stock_documents` WRITE;
/*!40000 ALTER TABLE `stock_documents` DISABLE KEYS */;
INSERT INTO `stock_documents` VALUES (36,'IN-TEST-1-1-in','in',1,1,50,3,NULL,'测试数据-in',3,'2026-11-17 10:00:00'),(37,'OUT-TEST-1-1-out','out',1,1,15,3,NULL,'测试数据-out',3,'2026-11-17 10:00:00'),(38,'IN-TEST-1-2-in','in',1,2,50,3,NULL,'测试数据-in',3,'2026-11-16 10:00:00'),(39,'OUT-TEST-1-2-out','out',1,2,15,3,NULL,'测试数据-out',3,'2026-11-16 10:00:00'),(40,'IN-TEST-1-3-in','in',1,3,50,3,NULL,'测试数据-in',3,'2026-11-15 10:00:00'),(41,'OUT-TEST-1-3-out','out',1,3,15,3,NULL,'测试数据-out',3,'2026-11-15 10:00:00'),(42,'IN-TEST-1-10-in','in',1,10,50,3,NULL,'测试数据-in',3,'2026-11-14 10:00:00'),(43,'OUT-TEST-1-10-out','out',1,10,15,3,NULL,'测试数据-out',3,'2026-11-14 10:00:00'),(44,'IN-TEST-1-11-in','in',1,11,50,3,NULL,'测试数据-in',3,'2026-11-13 10:00:00'),(45,'OUT-TEST-1-11-out','out',1,11,15,3,NULL,'测试数据-out',3,'2026-11-13 10:00:00'),(46,'IN-TEST-1-12-in','in',1,12,50,3,NULL,'测试数据-in',3,'2026-11-12 10:00:00'),(47,'OUT-TEST-1-12-out','out',1,12,15,3,NULL,'测试数据-out',3,'2026-11-12 10:00:00'),(48,'IN-TEST-2-1-in','in',2,1,50,3,NULL,'测试数据-in',3,'2026-11-17 10:00:00'),(49,'OUT-TEST-2-1-out','out',2,1,15,3,NULL,'测试数据-out',3,'2026-11-17 10:00:00'),(50,'IN-TEST-2-2-in','in',2,2,50,3,NULL,'测试数据-in',3,'2026-11-16 10:00:00'),(51,'OUT-TEST-2-2-out','out',2,2,15,3,NULL,'测试数据-out',3,'2026-11-16 10:00:00'),(52,'IN-TEST-2-3-in','in',2,3,50,3,NULL,'测试数据-in',3,'2026-11-15 10:00:00'),(53,'OUT-TEST-2-3-out','out',2,3,15,3,NULL,'测试数据-out',3,'2026-11-15 10:00:00'),(54,'IN-TEST-2-10-in','in',2,10,50,3,NULL,'测试数据-in',3,'2026-11-14 10:00:00'),(55,'OUT-TEST-2-10-out','out',2,10,15,3,NULL,'测试数据-out',3,'2026-11-14 10:00:00'),(56,'IN-TEST-2-11-in','in',2,11,50,3,NULL,'测试数据-in',3,'2026-11-13 10:00:00'),(57,'OUT-TEST-2-11-out','out',2,11,15,3,NULL,'测试数据-out',3,'2026-11-13 10:00:00'),(58,'IN-TEST-2-12-in','in',2,12,50,3,NULL,'测试数据-in',3,'2026-11-12 10:00:00'),(59,'OUT-TEST-2-12-out','out',2,12,15,3,NULL,'测试数据-out',3,'2026-11-12 10:00:00'),(60,'IN-TEST-4-1-in','in',4,1,50,3,NULL,'测试数据-in',3,'2026-11-17 10:00:00'),(61,'OUT-TEST-4-1-out','out',4,1,15,3,NULL,'测试数据-out',3,'2026-11-17 10:00:00'),(62,'IN-TEST-4-2-in','in',4,2,50,3,NULL,'测试数据-in',3,'2026-11-16 10:00:00'),(63,'OUT-TEST-4-2-out','out',4,2,15,3,NULL,'测试数据-out',3,'2026-11-16 10:00:00'),(64,'IN-TEST-4-3-in','in',4,3,50,3,NULL,'测试数据-in',3,'2026-11-15 10:00:00'),(65,'OUT-TEST-4-3-out','out',4,3,15,3,NULL,'测试数据-out',3,'2026-11-15 10:00:00'),(66,'IN-TEST-4-10-in','in',4,10,50,3,NULL,'测试数据-in',3,'2026-11-14 10:00:00'),(67,'OUT-TEST-4-10-out','out',4,10,15,3,NULL,'测试数据-out',3,'2026-11-14 10:00:00'),(68,'IN-TEST-4-11-in','in',4,11,50,3,NULL,'测试数据-in',3,'2026-11-13 10:00:00'),(69,'OUT-TEST-4-11-out','out',4,11,15,3,NULL,'测试数据-out',3,'2026-11-13 10:00:00'),(70,'IN-TEST-4-12-in','in',4,12,50,3,NULL,'测试数据-in',3,'2026-11-12 10:00:00'),(71,'OUT-TEST-4-12-out','out',4,12,15,3,NULL,'测试数据-out',3,'2026-11-12 10:00:00');
/*!40000 ALTER TABLE `stock_documents` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `stock_ledgers`
--

DROP TABLE IF EXISTS `stock_ledgers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `stock_ledgers` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `doc_no` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '单据号',
  `doc_type` varchar(8) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'in/out',
  `warehouse_id` int(11) NOT NULL COMMENT '仓库',
  `material_id` int(11) NOT NULL COMMENT '物料',
  `quantity` int(11) NOT NULL COMMENT '变动数量',
  `before_balance` int(11) NOT NULL COMMENT '变动前余额',
  `after_balance` int(11) NOT NULL COMMENT '变动后余额',
  `related_order_id` int(11) DEFAULT NULL COMMENT '关联工单',
  `handler_id` int(11) DEFAULT NULL COMMENT '经手人',
  `remark` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '摘要',
  `created_at` datetime NOT NULL COMMENT '变动时间',
  PRIMARY KEY (`id`),
  KEY `handler_id` (`handler_id`),
  KEY `ix_ledger_mat_created` (`material_id`,`created_at`),
  KEY `ix_ledger_wh_type_created` (`warehouse_id`,`doc_type`,`created_at`),
  KEY `ix_ledger_order` (`related_order_id`),
  CONSTRAINT `stock_ledgers_ibfk_1` FOREIGN KEY (`handler_id`) REFERENCES `users` (`id`),
  CONSTRAINT `stock_ledgers_ibfk_2` FOREIGN KEY (`material_id`) REFERENCES `materials` (`id`),
  CONSTRAINT `stock_ledgers_ibfk_3` FOREIGN KEY (`related_order_id`) REFERENCES `work_orders` (`id`),
  CONSTRAINT `stock_ledgers_ibfk_4` FOREIGN KEY (`warehouse_id`) REFERENCES `warehouses` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=72 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `stock_ledgers`
--

LOCK TABLES `stock_ledgers` WRITE;
/*!40000 ALTER TABLE `stock_ledgers` DISABLE KEYS */;
INSERT INTO `stock_ledgers` VALUES (36,'IN-TEST-1-1-in','in',1,1,50,30,80,NULL,3,'测试数据流水','2026-11-17 10:00:00'),(37,'OUT-TEST-1-1-out','out',1,1,15,80,65,NULL,3,'测试数据流水','2026-11-17 10:00:00'),(38,'IN-TEST-1-2-in','in',1,2,50,35,85,NULL,3,'测试数据流水','2026-11-16 10:00:00'),(39,'OUT-TEST-1-2-out','out',1,2,15,85,70,NULL,3,'测试数据流水','2026-11-16 10:00:00'),(40,'IN-TEST-1-3-in','in',1,3,50,40,90,NULL,3,'测试数据流水','2026-11-15 10:00:00'),(41,'OUT-TEST-1-3-out','out',1,3,15,90,75,NULL,3,'测试数据流水','2026-11-15 10:00:00'),(42,'IN-TEST-1-10-in','in',1,10,50,45,95,NULL,3,'测试数据流水','2026-11-14 10:00:00'),(43,'OUT-TEST-1-10-out','out',1,10,15,95,80,NULL,3,'测试数据流水','2026-11-14 10:00:00'),(44,'IN-TEST-1-11-in','in',1,11,50,50,100,NULL,3,'测试数据流水','2026-11-13 10:00:00'),(45,'OUT-TEST-1-11-out','out',1,11,15,100,85,NULL,3,'测试数据流水','2026-11-13 10:00:00'),(46,'IN-TEST-1-12-in','in',1,12,50,55,105,NULL,3,'测试数据流水','2026-11-12 10:00:00'),(47,'OUT-TEST-1-12-out','out',1,12,15,105,90,NULL,3,'测试数据流水','2026-11-12 10:00:00'),(48,'IN-TEST-2-1-in','in',2,1,50,60,110,NULL,3,'测试数据流水','2026-11-17 10:00:00'),(49,'OUT-TEST-2-1-out','out',2,1,15,110,95,NULL,3,'测试数据流水','2026-11-17 10:00:00'),(50,'IN-TEST-2-2-in','in',2,2,50,65,115,NULL,3,'测试数据流水','2026-11-16 10:00:00'),(51,'OUT-TEST-2-2-out','out',2,2,15,115,100,NULL,3,'测试数据流水','2026-11-16 10:00:00'),(52,'IN-TEST-2-3-in','in',2,3,50,70,120,NULL,3,'测试数据流水','2026-11-15 10:00:00'),(53,'OUT-TEST-2-3-out','out',2,3,15,120,105,NULL,3,'测试数据流水','2026-11-15 10:00:00'),(54,'IN-TEST-2-10-in','in',2,10,50,75,125,NULL,3,'测试数据流水','2026-11-14 10:00:00'),(55,'OUT-TEST-2-10-out','out',2,10,15,125,110,NULL,3,'测试数据流水','2026-11-14 10:00:00'),(56,'IN-TEST-2-11-in','in',2,11,50,80,130,NULL,3,'测试数据流水','2026-11-13 10:00:00'),(57,'OUT-TEST-2-11-out','out',2,11,15,130,115,NULL,3,'测试数据流水','2026-11-13 10:00:00'),(58,'IN-TEST-2-12-in','in',2,12,50,85,135,NULL,3,'测试数据流水','2026-11-12 10:00:00'),(59,'OUT-TEST-2-12-out','out',2,12,15,135,120,NULL,3,'测试数据流水','2026-11-12 10:00:00'),(60,'IN-TEST-4-1-in','in',4,1,50,90,140,NULL,3,'测试数据流水','2026-11-17 10:00:00'),(61,'OUT-TEST-4-1-out','out',4,1,15,140,125,NULL,3,'测试数据流水','2026-11-17 10:00:00'),(62,'IN-TEST-4-2-in','in',4,2,50,95,145,NULL,3,'测试数据流水','2026-11-16 10:00:00'),(63,'OUT-TEST-4-2-out','out',4,2,15,145,130,NULL,3,'测试数据流水','2026-11-16 10:00:00'),(64,'IN-TEST-4-3-in','in',4,3,50,100,150,NULL,3,'测试数据流水','2026-11-15 10:00:00'),(65,'OUT-TEST-4-3-out','out',4,3,15,150,135,NULL,3,'测试数据流水','2026-11-15 10:00:00'),(66,'IN-TEST-4-10-in','in',4,10,50,105,155,NULL,3,'测试数据流水','2026-11-14 10:00:00'),(67,'OUT-TEST-4-10-out','out',4,10,15,155,140,NULL,3,'测试数据流水','2026-11-14 10:00:00'),(68,'IN-TEST-4-11-in','in',4,11,50,110,160,NULL,3,'测试数据流水','2026-11-13 10:00:00'),(69,'OUT-TEST-4-11-out','out',4,11,15,160,145,NULL,3,'测试数据流水','2026-11-13 10:00:00'),(70,'IN-TEST-4-12-in','in',4,12,50,115,165,NULL,3,'测试数据流水','2026-11-12 10:00:00'),(71,'OUT-TEST-4-12-out','out',4,12,15,165,150,NULL,3,'测试数据流水','2026-11-12 10:00:00');
/*!40000 ALTER TABLE `stock_ledgers` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `stock_warning_states`
--

DROP TABLE IF EXISTS `stock_warning_states`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `stock_warning_states` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `warehouse_id` int(11) NOT NULL COMMENT '仓库',
  `material_id` int(11) NOT NULL COMMENT '物料',
  `is_low` tinyint(1) NOT NULL COMMENT '当前是否低位',
  `last_notified_at` datetime DEFAULT NULL COMMENT '最近推送时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_stock_warn_wh_mat` (`warehouse_id`,`material_id`),
  KEY `material_id` (`material_id`),
  CONSTRAINT `stock_warning_states_ibfk_1` FOREIGN KEY (`material_id`) REFERENCES `materials` (`id`),
  CONSTRAINT `stock_warning_states_ibfk_2` FOREIGN KEY (`warehouse_id`) REFERENCES `warehouses` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `stock_warning_states`
--

LOCK TABLES `stock_warning_states` WRITE;
/*!40000 ALTER TABLE `stock_warning_states` DISABLE KEYS */;
/*!40000 ALTER TABLE `stock_warning_states` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_roles`
--

DROP TABLE IF EXISTS `user_roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `user_roles` (
  `user_id` int(11) NOT NULL,
  `role_id` int(11) NOT NULL,
  PRIMARY KEY (`user_id`,`role_id`),
  KEY `role_id` (`role_id`),
  CONSTRAINT `user_roles_ibfk_1` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`),
  CONSTRAINT `user_roles_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_roles`
--

LOCK TABLES `user_roles` WRITE;
/*!40000 ALTER TABLE `user_roles` DISABLE KEYS */;
INSERT INTO `user_roles` VALUES (1,1),(2,2),(3,3),(4,4),(5,5),(15,5),(16,5),(17,5),(18,5),(19,5),(20,5),(21,5),(22,5),(6,6);
/*!40000 ALTER TABLE `user_roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `users` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '登录名',
  `employee_no` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '工号',
  `name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '真实姓名',
  `email` varchar(120) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '邮箱，可空',
  `phone` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '手机号，可空',
  `password_hash` varchar(256) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '密码哈希',
  `position` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '岗位',
  `department_id` int(11) DEFAULT NULL COMMENT '单部门归属，可空',
  `hire_date` date DEFAULT NULL COMMENT '入职日期',
  `leave_date` date DEFAULT NULL COMMENT '离职日期',
  `is_active` tinyint(1) NOT NULL COMMENT '离职=停用',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `employee_no` (`employee_no`),
  UNIQUE KEY `username` (`username`),
  KEY `department_id` (`department_id`),
  CONSTRAINT `users_ibfk_1` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=23 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'admin','EMP0001','系统管理员',NULL,NULL,'pbkdf2:sha256:600000$YI2N84GoCElFBah3$6b299ea0f662b58c322282143e5f52fbd40522d4cf20a2fe637990e61749142e','信息化负责人',NULL,'2026-11-18',NULL,1,'2026-11-18 02:03:17'),(2,'leader1','EMP0002','张主管',NULL,NULL,'pbkdf2:sha256:600000$wiwz1ER9lIvQE2Xk$626479b36a87ec4be88fb7d99520ac5ddc37ed5d4d77a97f47a9a3b6a979e801','生产主管',1,'2026-11-18',NULL,1,'2026-11-18 02:03:17'),(3,'keeper1','EMP0003','王仓管',NULL,NULL,'pbkdf2:sha256:600000$MszSeBCAVIKTxIsw$ffbd0ef1ce902f2523e4a06b54226f651fe301bb0a1a2d2d92495214952a98ad','仓库管理员',2,'2026-11-18',NULL,1,'2026-11-18 02:03:17'),(4,'producer1','EMP0004','刘生产',NULL,NULL,'pbkdf2:sha256:600000$j8wlcDPZ9F9E4tQZ$80d21963e3228b3f779789b33578c231c5be51df3d9a0571aa2035cf7d038dc8','生产调度',1,'2026-11-18',NULL,1,'2026-11-18 02:03:17'),(5,'staff1','EMP0005','赵员工',NULL,NULL,'pbkdf2:sha256:600000$EVCkcQT4ozpeb6HU$dc8adfc6971bb915e4d9b443527bbc94acbe86eb09a0ba184002ca5f7e7e91e7','操作工',1,'2026-11-18',NULL,1,'2026-11-18 02:03:17'),(6,'arch1','EMP0006','陈档案',NULL,NULL,'pbkdf2:sha256:600000$K8JZkBTRNddxRqvH$fada536612235b80d852040aad83c9cc943b2017bc8e22fd2fcb1bb6469f4697','档案管理员',3,'2026-11-18',NULL,1,'2026-11-18 02:03:17'),(15,'staff2','EMP0007','钱师傅',NULL,'13810000000','pbkdf2:sha256:600000$QejNTlFOEwSS9CXc$08a11e28918ccf487705b9348ffe2b9b55d9f6b444e6fc5c04d0a9f6d8fc5c98','装配工',8,'2026-05-02',NULL,1,'2026-11-18 02:04:05'),(16,'staff3','EMP0008','孙师傅',NULL,'13810000001','pbkdf2:sha256:600000$EodUzVxY8Cs2hoCn$d8c9308b72bc536c4f01a2f59c92ee59bf1a2fecb026e3826edea78fc0bde739','焊工',8,'2026-05-02',NULL,1,'2026-11-18 02:04:05'),(17,'staff4','EMP0009','周师傅',NULL,'13810000002','pbkdf2:sha256:600000$xLIFcPd3qS9mVz8I$f26ec8f99165a70a2df8f657118c4808b669e7c554c38fecc7f9cac9f9c08b60','操作工',9,'2026-05-02',NULL,1,'2026-11-18 02:04:05'),(18,'staff5','EMP0010','吴师傅',NULL,'13810000003','pbkdf2:sha256:600000$fLtJzLMXo0Ehvghu$a3f0638956ded50bd6b93f370992a52318a282b7cd6a13e5e9375d2cb783d1b9','操作工',9,'2026-05-02',NULL,1,'2026-11-18 02:04:05'),(19,'staff6','EMP0011','郑质检',NULL,'13810000004','pbkdf2:sha256:600000$H650ewgfMjhGjhoa$00b66b7fe36bc37ed31cd226a21e80050839e0e005a6c10df91f998d029c4955','质检员',10,'2026-05-02',NULL,1,'2026-11-18 02:04:05'),(20,'staff7','EMP0012','冯库工',NULL,'13810000005','pbkdf2:sha256:600000$ISl8A7z53JDJiqck$69a6ed09061f82383d362c8deaff1acd09229f3d55a4c91e4725018c0c94cc0c','库工',11,'2026-05-02',NULL,1,'2026-11-18 02:04:06'),(21,'staff8','EMP0013','陈文员',NULL,'13810000006','pbkdf2:sha256:600000$0WeecevR1vzRzMtz$90f377b627ab2d51a49b4e7e3523993c267e7ef3214ddc17fdbaf4403a20c8ac','文员',NULL,'2026-05-02',NULL,1,'2026-11-18 02:04:06'),(22,'staff9','EMP0014','褚学徒',NULL,'13810000007','pbkdf2:sha256:600000$aJIIdeWDKtHDwLk9$ebe43b9b7a9ccfacec559da0a8c9646ef3185f4a87f5f97fbfafd45522b5b78c','学徒',8,'2026-05-02',NULL,1,'2026-11-18 02:04:06');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `warehouses`
--

DROP TABLE IF EXISTS `warehouses`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `warehouses` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '仓库名称',
  `location` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '位置',
  `is_active` tinyint(1) NOT NULL COMMENT '停用=软删',
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `warehouses`
--

LOCK TABLES `warehouses` WRITE;
/*!40000 ALTER TABLE `warehouses` DISABLE KEYS */;
INSERT INTO `warehouses` VALUES (1,'原材料仓','1号厂房东侧',1),(2,'成品仓','2号厂房',1),(4,'半成品仓','1号厂房西侧',1);
/*!40000 ALTER TABLE `warehouses` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `work_order_steps`
--

DROP TABLE IF EXISTS `work_order_steps`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `work_order_steps` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `work_order_id` int(11) NOT NULL COMMENT '所属工单',
  `name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '工序名',
  `seq` int(11) NOT NULL COMMENT '顺序号',
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '状态',
  `operator_id` int(11) DEFAULT NULL COMMENT '操作人，可空',
  `started_at` datetime DEFAULT NULL COMMENT '开始时间',
  `finished_at` datetime DEFAULT NULL COMMENT '完成时间',
  `remark` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '备注',
  PRIMARY KEY (`id`),
  KEY `operator_id` (`operator_id`),
  KEY `work_order_id` (`work_order_id`),
  CONSTRAINT `work_order_steps_ibfk_1` FOREIGN KEY (`operator_id`) REFERENCES `users` (`id`),
  CONSTRAINT `work_order_steps_ibfk_2` FOREIGN KEY (`work_order_id`) REFERENCES `work_orders` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=19 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `work_order_steps`
--

LOCK TABLES `work_order_steps` WRITE;
/*!40000 ALTER TABLE `work_order_steps` DISABLE KEYS */;
INSERT INTO `work_order_steps` VALUES (1,1,'下料',1,'pending',NULL,NULL,NULL,''),(2,1,'组装',2,'pending',NULL,NULL,NULL,''),(3,1,'质检',3,'pending',NULL,NULL,NULL,''),(4,2,'下料',1,'in_progress',NULL,NULL,NULL,''),(5,2,'组装',2,'pending',NULL,NULL,NULL,''),(6,2,'质检',3,'pending',NULL,NULL,NULL,''),(7,3,'下料',1,'in_progress',NULL,NULL,NULL,''),(8,3,'组装',2,'pending',NULL,NULL,NULL,''),(9,3,'质检',3,'pending',NULL,NULL,NULL,''),(10,4,'下料',1,'completed',NULL,NULL,NULL,''),(11,4,'组装',2,'completed',NULL,NULL,NULL,''),(12,4,'质检',3,'pending',NULL,NULL,NULL,''),(13,5,'下料',1,'completed',NULL,NULL,NULL,''),(14,5,'组装',2,'completed',NULL,NULL,NULL,''),(15,5,'质检',3,'completed',NULL,NULL,NULL,''),(16,6,'下料',1,'in_progress',NULL,NULL,NULL,''),(17,6,'组装',2,'pending',NULL,NULL,NULL,''),(18,6,'质检',3,'pending',NULL,NULL,NULL,'');
/*!40000 ALTER TABLE `work_order_steps` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `work_orders`
--

DROP TABLE IF EXISTS `work_orders`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!40101 SET character_set_client = utf8 */;
CREATE TABLE `work_orders` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `order_no` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '单号 WO+日期+序号',
  `product_name` varchar(128) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '产品名称',
  `quantity` int(11) NOT NULL COMMENT '数量',
  `due_date` date DEFAULT NULL COMMENT '交期',
  `leader_id` int(11) DEFAULT NULL COMMENT '负责人',
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '状态',
  `remark` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '备注',
  `created_by` int(11) NOT NULL COMMENT '创建人',
  `created_at` datetime NOT NULL COMMENT '创建时间',
  `related_department_id` int(11) DEFAULT NULL COMMENT '归属部门',
  PRIMARY KEY (`id`),
  UNIQUE KEY `order_no` (`order_no`),
  KEY `created_by` (`created_by`),
  KEY `leader_id` (`leader_id`),
  KEY `ix_work_order_related_dept` (`related_department_id`),
  CONSTRAINT `work_orders_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`),
  CONSTRAINT `work_orders_ibfk_2` FOREIGN KEY (`leader_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `work_orders`
--

LOCK TABLES `work_orders` WRITE;
/*!40000 ALTER TABLE `work_orders` DISABLE KEYS */;
INSERT INTO `work_orders` VALUES (1,'WO20250101001','示例产品A',100,NULL,2,'pending','种子数据示例工单',1,'2026-11-18 02:03:17',NULL),(2,'WO-TEST-001','精密支架',500,'2026-11-28',2,'in_progress','测试数据工单',1,'2026-11-10 09:00:00',1),(3,'WO-TEST-002','控制盒外壳',300,'2026-11-28',2,'in_progress','测试数据工单',1,'2026-11-10 09:00:00',1),(4,'WO-TEST-003','连接器组件',1000,'2026-11-28',2,'completed','测试数据工单',1,'2026-11-10 09:00:00',1),(5,'WO-TEST-004','包装套件',2000,'2026-11-28',2,'accepted','测试数据工单',1,'2026-11-10 09:00:00',1),(6,'WO-TEST-005','传感器底座',150,'2026-11-28',2,'pending','测试数据工单',1,'2026-11-10 09:00:00',1);
/*!40000 ALTER TABLE `work_orders` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping routines for database 'factory manager'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-11-18  2:19:05
