create table blockchain
(
no number,
previousHash varchar2(1000),
timestamp varchar2(1000),
data varchar2(1000),
currentHash varchar2(1000),
proof number,
fee BINARY_DOUBLE,
signature varchar2(1000),
constraints blockchain_PK primary key (no)
);

create table txdata
(
commitYN number,
sender varchar2(1000),
amount BINARY_DOUBLE,
receiver varchar2(1000),
uuid varchar2(1000),
fee BINARY_DOUBLE,
message varchar2(1000),
txTime varchar2(1000)
);

create table nodelist
(
ip varchar2(1000),
port varchar2(1000),
trial number
);

select * from blockchain;

select * from txdata;

select * from nodelist;

truncate table blockchain;

truncate table txdata;

truncate table nodelist;

insert into nodelist values ('127.0.0.1', '8099', 0)

update txdata set commityn = 0

update txdata set commityn = 1 where uuid = 'bd9ab965-facf-408b-aea5-875f97fc8be3'