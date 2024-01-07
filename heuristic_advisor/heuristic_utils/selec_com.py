import os
import sys
import copy
import json
import logging
import pickle
import argparse
import configparser

from heuristic_advisor.heuristic_utils.workload import Workload, Table, Column, Query


def get_parser():
    parser = argparse.ArgumentParser(
        description="the testbed of Heuristic-based Index Advisors.")

    parser.add_argument("--exp_id", type=str, default="extend_exp_id")
    parser.add_argument("--sel_params", type=str, default="parameters")
    parser.add_argument("--exp_conf_file", type=str,
                        default="../data_resource/heuristic_conf/extend_config.json")
    parser.add_argument("--work_type", type=str, default="not_template")
    parser.add_argument("--work_file", type=str,
                        default="/data/wz/index/attack/tpch_template_21.sql")

    parser.add_argument("--log_file", type=str,
                        default="./exp_res/{}/exp_runtime.log")
    parser.add_argument("--index_save_file", type=str,
                        default="./exp_res/{}/index_res.log")
    parser.add_argument("--res_save_file", type=str,
                        default="./exp_res/{}/sql_res.json")
    parser.add_argument("--db_conf_file", type=str,
                        default="../data_resource/database_conf/db_info.conf")
    parser.add_argument("--schema_file", type=str,
                        default="../data_resource/database_conf/schema_tpch.json")

    return parser


def get_conf(conf_file):
    conf = configparser.ConfigParser()
    conf.read(conf_file)

    return conf


def parse_command_line_args():
    arguments = sys.argv
    if "CRITICAL_LOG" in arguments:
        logging.getLogger().setLevel(logging.CRITICAL)
    if "ERROR_LOG" in arguments:
        logging.getLogger().setLevel(logging.ERROR)
    if "INFO_LOG" in arguments:
        logging.getLogger().setLevel(logging.INFO)
    for argument in arguments:
        if ".json" in argument:
            return argument


def set_logger(log_file):
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s: - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')

    # log to file
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)

    # log to console
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)

    logger.addHandler(ch)
    logger.addHandler(fh)


def find_parameter_list(algorithm_config, params="parameters"):
    parameters = algorithm_config[params]
    configs = []
    if parameters:
        # if more than one list --> raise
        # Only support one param list in each algorithm.
        counter = 0
        for key, value in parameters.items():
            if isinstance(value, list):
                counter += 1
        if counter > 1:
            raise Exception("Too many parameter lists in config.")

        for key, value in parameters.items():
            if isinstance(value, list):
                for i in value:
                    new_config = copy.deepcopy(algorithm_config)
                    new_config["parameters"][key] = i
                    configs.append(new_config)
    if len(configs) == 0:
        configs.append(algorithm_config)

    return configs


def get_columns_from_db(db_connector):
    tables, columns = list(), list()
    for table in db_connector.get_tables():
        table_object = Table(table)
        tables.append(table_object)
        for col in db_connector.get_cols(table):
            column_object = Column(col)
            table_object.add_column(column_object)
            columns.append(column_object)

    return tables, columns


def get_columns_from_schema(schema_file):
    tables, columns = list(), list()
    with open(schema_file, "r") as rf:
        db_schema = json.load(rf)

    for item in db_schema:
        table_object = Table(item["table"])
        tables.append(table_object)
        for col_info in item["columns"]:
            column_object = Column(col_info["name"])
            table_object.add_column(column_object)
            columns.append(column_object)

    return tables, columns


def read_row_query(sql_list, exp_conf, columns, type="template"):
    workload = list()
    for query_id, query_text in enumerate(sql_list):
        if type == "template" and exp_conf["queries"] \
                and query_id+1 not in exp_conf["queries"]:
            continue

        query = Query(query_id, query_text)
        for column in columns:
            # if column.name in query.text and column.table.name in query.text:
            # if " " + column.name + " " in query.text and column.table.name in query.text:
            if column.name in query.text:
                query.columns.append(column)
        workload.append(query)

    logging.info("Queries read.")
    return workload


# --- Unit conversions ---
# Storage
def b_to_mb(b):
    """
    1024?
    :param b:
    :return:
    """
    return b / 1000 / 1000


def mb_to_b(mb):
    return mb * 1000 * 1000


# Time
def s_to_ms(s):
    return s * 1000


# --- Index selection utilities ---
def indexes_by_table(indexes):
    indexes_by_table = {}
    for index in indexes:
        table = index.table()
        if table not in indexes_by_table:
            indexes_by_table[table] = []

        indexes_by_table[table].append(index)

    return indexes_by_table


def get_utilized_indexes(
    workload, indexes_per_query, cost_evaluation, detailed_query_information=False
):
    utilized_indexes_workload = set()
    query_details = {}
    for query, indexes in zip(workload.queries, indexes_per_query):
        (
            utilized_indexes_query,
            cost_with_indexes,
        ) = cost_evaluation.which_indexes_utilized_and_cost(query, indexes)
        utilized_indexes_workload |= utilized_indexes_query

        if detailed_query_information:
            cost_without_indexes = cost_evaluation.calculate_cost(
                Workload([query]), indexes=[]
            )

            query_details[query] = {
                "cost_without_indexes": cost_without_indexes,
                "cost_with_indexes": cost_with_indexes,
                "utilized_indexes": utilized_indexes_query,
            }

    return utilized_indexes_workload, query_details
