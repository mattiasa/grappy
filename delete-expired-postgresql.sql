delete from greylist where n=1 and last < date_part('epoch', current_timestamp) - 86400;
