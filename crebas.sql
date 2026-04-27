/*==============================================================*/
/* DBMS name:      MySQL 8.0                                    */
/* Created on:     2026/4/27 22:12:58                           */
/*==============================================================*/


set foreign_key_checks = 0;

drop table if exists telemetry_record;

drop table if exists device_trait;

drop table if exists event_instance;

drop table if exists device;

drop table if exists trait_type;

drop table if exists event_type;

drop table if exists user;

set foreign_key_checks = 1;

/*==============================================================*/
/* Table: device                                                */
/*==============================================================*/
create table device
(
   device_id            BIGINT not null,
   user_id              BIGINT not null,
   device_sn            VARCHAR(50)	 not null,
   device_name          VARCHAR(50) not null,
   pet_name             VARCHAR(30) not null,
   is_online            TINYINT,
   activate_time        DATETIME(3),
   create_time          DATETIME(3) not null,
   update_time          DATETIME(3) not null,
   primary key (device_id)
);

alter table device comment '�û��󶨵ĳ���ڵ��豸��Ϣ';

/*==============================================================*/
/* Table: device_trait                                          */
/*==============================================================*/
create table device_trait
(
   device_id            BIGINT not null,
   trait_type_id        BIGINT not null,
   is_enabled           TINYINT not null,
   create_time          DATETIME(3) not null,
   primary key (device_id, trait_type_id)
);

alter table device_trait comment 'device��trait_type��Զ��м��';

/*==============================================================*/
/* Table: event_instance                                        */
/*==============================================================*/
create table event_instance
(
   event_instance_id    BIGINT not null,
   device_id            BIGINT not null,
   event_type_id        BIGINT not null,
   status               TINYINT not null,
   event_content        	VARCHAR(500),
   start_time           DATETIME(3) not null,
   end_time             DATETIME(3),
   primary key (event_instance_id)
);

alter table event_instance comment '�豸�������¼�ʵ����¼';

/*==============================================================*/
/* Index: idx_device_status_time                                */
/*==============================================================*/
create index idx_device_status_time on event_instance
(
   device_id,
   status,
   start_time
);

/*==============================================================*/
/* Table: event_type                                            */
/*==============================================================*/
create table event_type
(
   event_type_id        BIGINT not null,
   event_code           VARCHAR(50) not null,
   event_name           VARCHAR(50) not null,
   event_level          TINYINT not null,
   create_time          DATETIME(3) not null,
   primary key (event_type_id)
);

alter table event_type comment '�豸�澯/�¼����Ͷ��壨��͵�����Χ��Խ�磩';

/*==============================================================*/
/* Table: telemetry_record                                      */
/*==============================================================*/
create table telemetry_record
(
   record_id            BIGINT not null,
   user_id              BIGINT not null,
   device_id            BIGINT not null,
   event_instance_id    BIGINT,
   trait_type_id        BIGINT not null,
   trait_value          VARCHAR(100) not null,
   timestamp            DATETIME(3) not null,
   primary key (record_id)
);

alter table telemetry_record comment '�豸�ϱ���ʵʱң�����ݺ��ı�';

/*==============================================================*/
/* Index: idx_device_timestamp                                  */
/*==============================================================*/
create index idx_device_timestamp on telemetry_record
(
   device_id,
   timestamp
);

/*==============================================================*/
/* Index: idx_user_timestamp                                    */
/*==============================================================*/
create index idx_user_timestamp on telemetry_record
(
   user_id,
   timestamp
);

/*==============================================================*/
/* Index: idx_timestamp                                         */
/*==============================================================*/
create index idx_timestamp on telemetry_record
(
   timestamp
);

/*==============================================================*/
/* Table: trait_type                                            */
/*==============================================================*/
create table trait_type
(
   trait_type_id        BIGINT not null,
   trait_code           VARCHAR(50)	 not null,
   trait_name           VARCHAR(50) not null,
   trait_unit           VARCHAR(20),
   create_time          DATETIME(3) not null,
   primary key (trait_type_id)
);

alter table trait_type comment '�豸֧�ֵ�ң�����Զ��壨�����¡����ʡ���λ��';

/*==============================================================*/
/* Table: user                                                  */
/*==============================================================*/
create table user
(
   user_id              BIGINT not null,
   username             VARCHAR(50) not null,
   password_hash        VARCHAR(255) not null,
   phone                VARCHAR(11),
   nick_name            VARCHAR(30) not null,
   create_time          DATETIME(3) not null,
   update_time          DATETIME(3) not null,
   primary key (user_id)
);

alter table user comment 'PetNodeϵͳע���û���Ϣ';

alter table device add constraint FK_Reference_1 foreign key (user_id)
      references user (user_id) on delete restrict on update restrict;

alter table device_trait add constraint FK_Reference_7 foreign key (device_id)
      references device (device_id) on delete restrict on update restrict;

alter table device_trait add constraint FK_Reference_8 foreign key (trait_type_id)
   references trait_type (trait_type_id) on delete restrict on update restrict;

alter table event_instance add constraint FK_Reference_2 foreign key (device_id)
      references device (device_id) on delete restrict on update restrict;

alter table event_instance add constraint FK_Reference_3 foreign key (event_type_id)
      references event_type (event_type_id) on delete restrict on update restrict;

alter table telemetry_record add constraint FK_Reference_4 foreign key (user_id)
      references user (user_id) on delete restrict on update restrict;

alter table telemetry_record add constraint FK_Reference_5 foreign key (device_id)
      references device (device_id) on delete restrict on update restrict;

alter table telemetry_record add constraint FK_Reference_6 foreign key (event_instance_id)
      references event_instance (event_instance_id) on delete restrict on update restrict;

alter table telemetry_record add constraint FK_Reference_9 foreign key (trait_type_id)
   references trait_type (trait_type_id) on delete restrict on update restrict;

