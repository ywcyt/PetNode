# AutoScale Proof Summary

## Run
- run_id: 20260416_160726
- proof_dir: D:\bot\PetNode\C_end_Simulator\output_data\proof_20260416_160726

## JMeter
- total_requests: 1000
- success_requests: 1000
- error_requests: 0
- avg_elapsed_ms: 4.81
- p95_elapsed_ms: 6

## AutoScale Evidence
- max_workers: 1
- max_messages_ready: 0
- max_messages_unack: 0

## Files
- JMeter JTL: D:\bot\PetNode\C_end_Simulator\output_data\proof_20260416_160726\jmeter_result.jtl
- JMeter Report: D:\bot\PetNode\C_end_Simulator\output_data\proof_20260416_160726\jmeter_report
- Monitor CSV: D:\bot\PetNode\C_end_Simulator\output_data\proof_20260416_160726\autoscale_monitor.csv
- AutoScaler Log: D:\bot\PetNode\C_end_Simulator\output_data\proof_20260416_160726\autoscaler.log

## Pass Criteria
1. Scale-up observed: max_workers > 1
2. Queue pressure observed: max_messages_ready or max_messages_unack > 0
3. High request success: success rate >= 95%