-- Create greylist database in MySQL

-- create database greylist;

use greylist;

drop table greylist;

create table greylist (
                ip varchar(40) not null, 
                sender varchar(100) not null, 
                recipient varchar(100) not null, 
                first integer not null, 
                last integer not null,
		n integer not null,
                primary key (ip,sender,recipient)
                );

drop table whitelist;

create table whitelist (
		ip varchar(40),
                sender varchar(100),
                recipient varchar(100),
		comment varchar(200)
		);

grant all on greylist to greylist;
grant all on whitelist to greylist;
