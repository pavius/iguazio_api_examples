#!/usr/bin/env bash

# Submit a spark job to consume the stream data
spark-submit --master yarn --py-files ~/igz/bigdata/libs/v3io-py.zip consume_drivers_stream_data.py

