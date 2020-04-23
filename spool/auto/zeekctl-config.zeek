redef Pcap::snaplen = 9216;
redef Pcap::bufsize = 128;

redef global_hash_seed = "55030b22";

redef Cluster::default_store_dir = "/zeek/spool/stores";
redef LogAscii::use_json=T;
