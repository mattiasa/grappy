-- Create greylist database in MySQL

-- create database greylist;

use greylist;

-- drop table triplets;

create table greylist (
                ip varchar(40) not null, 
                sender varchar(100) not null, 
                recipient varchar(100) not null, 
                first integer not null, 
                last integer not null,
                primary key (ip,sender,recipient),
                index last_index(last)
                );

create table whitelist (
		ip varchar(40),
                sender varchar(100),
                recipient varchar(100),
		comment varchar(200)
		);
