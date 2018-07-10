import requests
import json
import os
import s2sphere

# Get configuration information from environment variables defined using Nuclio
WEBAPI_URL     = str(os.getenv('WEBAPI_URL'))
CONTAINER_NAME = str(os.getenv('CONTAINER_NAME'))

WEBAPI_USER = str(os.getenv('WEBAPI_USER'))
WEBAPI_PASSWORD = str(os.getenv('WEBAPI_PASSWORD'))
WEBAPI_CRED = str(os.getenv('WEBAPI_CRED'))

# Get table locations from environment variables defined using Nuclio
DRIVERS_TABLE_PATH = CONTAINER_NAME + str(os.getenv('DRIVERS_TABLE'))
PASSENGERS_TABLE_PATH = CONTAINER_NAME + str(os.getenv('PASSENGERS_TABLE'))
CELLS_TABLE_PATH   = CONTAINER_NAME + str(os.getenv('CELLS_TABLE'))

DRIVER_PREFIX =F 'drivers_'
PASSENGER_PREFIX = 'passengers_'

V3IO_HEADER_FUNCTION = 'X-v3io-function'

def handler(context, event):

    # Read the data to be ingested from the input json
    input_data_json = event.body 
    input_data = json.loads(input_data_json)

    record_type = str(input_data ["RecordType"])

    id = str(input_data ["ID"])
    
    longitude = float (input_data["longitude"])
    latitude = float (input_data["latitude"])

    # Use google s2Sphere library to calculate Cell from longitude and latitude
    p1 = s2sphere.LatLng.from_degrees(latitude,longitude)
    cell = s2sphere.CellId.from_lat_lng(p1).parent(15)
    cell_id = str(cell.id())
    
    # Create a session for sending NoSQL Webapi requests
    s = requests.Session()

    # Provide webapi user/pass
    if WEBAPI_USER is not None and WEBAPI_PASSWORD is not None:
        s.auth = (WEBAPI_USER, WEBAPI_PASSWORD)
    
    # Ingestion of both drivers and passengers are supported
    # Depening on record type, releavant tables will be updated
    if record_type == 'driver':
        ITEM_PREFIX = DRIVER_PREFIX
        ITEM_PATH   = DRIVERS_TABLE_PATH
    else :
        ITEM_PREFIX = PASSENGER_PREFIX
        ITEM_PATH = PASSENGERS_TABLE_PATH

    # update driver current and previous location 
    res = ngx_update_expression_request(s,WEBAPI_URL, ITEM_PATH + ITEM_PREFIX +id, None, None,
                                            None,
                                            "SET previous_cell_id=if_not_exists(current_cell_id,0);current_cell_id=" + cell_id + ";change_cell_id_indicator=(previous_cell_id != current_cell_id);",
                                            None)

    # context.logger.info(res)
    
    # Get current and previous cell for driver 
    response_json = ngx_get_item_request(s,WEBAPI_URL, ITEM_PATH + ITEM_PREFIX +id,None,None,exp_attrs=["change_cell_id_indicator","current_cell_id","previous_cell_id"])

    # Check if a cell update is needed
    attrs = response_json["Item"]
    change_cell_id_indicator_val = attrs["change_cell_id_indicator"]["BOOL"]
    current_cell_id_val = attrs["current_cell_id"]["N"]
    previous_cell_id_val = attrs["previous_cell_id"]["N"]

    # if cell was changed, increase the count on the new cell and descrease from the old cell
    if change_cell_id_indicator_val:
            # Increase the count on the currnet cell
            res=ngx_update_expression_request(s,WEBAPI_URL, CELLS_TABLE_PATH + "cell_"+ current_cell_id_val, None, None,
                                          None,
                                          "SET "+ITEM_PREFIX+"count=if_not_exists("+ITEM_PREFIX+"count,0)+1;",
                                          None)

            # context.logger.info(res)

            # Decrease the count on the previous cell
            res = ngx_update_expression_request(s,WEBAPI_URL, CELLS_TABLE_PATH + "cell_" + previous_cell_id_val, None, None,None,
                                          "SET "+ITEM_PREFIX+"count="+ITEM_PREFIX+"count-1;",
                                          None)

            # context.logger.info(res)

    return context.Response(body='Ingestion completed successfully',
                            headers={},
                            content_type='text/plain',
                            status_code=200)

#
# Construct and send GetItem NoSQL Web API reuest
#
def ngx_get_item_request(
        s,base_url, path_in_url, table_name=None, key=None, exp_attrs=None, expected_result=requests.codes.ok):
    url = base_url + path_in_url

    #
    # Construct the json     
    #
    request_json = {}

    if table_name is not None:
        request_json["TableName"] = table_name

    request_json["AttributesToGet"] = ""

    for attr_name in exp_attrs:
        if request_json["AttributesToGet"] != "":
            request_json["AttributesToGet"] += ","
        request_json["AttributesToGet"] += attr_name

    payload = json.dumps(request_json)
    
    headers = {V3IO_HEADER_FUNCTION: 'GetItem',"Authorization": WEBAPI_CRED}
    
    # send the request
    res = s.put(url, data=payload, headers=headers)

    assert res.status_code == expected_result
    if expected_result != requests.codes.ok:
        return

    response_json = json.loads(res.content)
    return response_json

#
# Construct and send UpdateItem NoSQL Web API reuest
#
def ngx_update_expression_request(
        s,base_url, path_in_url, table_name=None, key=None, mode=None, update_expr=None, text_filter=None, type="UpdateItem",
        expected_result=requests.codes.no_content):
    url = base_url + path_in_url

    #
    # Construct the json     
    #
    request_json = {}

    if table_name is not None:
        request_json["TableName"] = table_name

    if mode is not None:
        request_json["UpdateMode"] = mode

    if update_expr is not None:
        request_json["UpdateExpression"] = update_expr

    if text_filter is not None:
        request_json["ConditionExpression"] = text_filter

    payload = json.dumps(request_json)
    headers = {V3IO_HEADER_FUNCTION: type ,"Authorization": WEBAPI_CRED}
 
    # send the request
    res = s.put(url, data=payload, headers=headers)
    #assert res.status_code == expected_result
    return res
