-- should be executed every hour by cron 

delete from greylist where n = 1 and last < UNIX_TIMESTAMP() - 86400;
