#! /usr/bin/env python3

from typing import List
from graphviz import Digraph
from graphviz.backend import render
import cantools
import click
import subprocess
import pathlib
import os
import tempfile

def sort_messages_by_CAN_id(msgs: list):
    i = 0
    while (i < len(msgs) - 2):
        if msgs[i].frame_id > msgs[i + 1].frame_id:
            tmp = msgs[i]
            msgs[i] = msgs[i+1]
            msgs[i+1] = tmp
            i = 0
        i += 1
    return msgs

def messages_from_a_to_b(messages: cantools.db.Message,
                         senders: List[str],
                         receivers: List[str]):
    """return all messages sent from any ecu_a to any ecu_b"""
    matching_messages = []
    msgs_to_search = [msg for msg in messages if any([sender in msg.senders for sender in senders])]
    for msg in msgs_to_search:
        for receiver in receivers:
            if any([receiver in sig.receivers for sig in msg.signals]):
                matching_messages.append(msg)
    return matching_messages

def to_hex_str(val: float):
    return hex(int(val * 255))[2:]

def color_str_for_msg(msg, min_id=0, max_id=0x7FF):
    """ makes lines representing higher priority (lower CAN ID) red """
    fmt = "#{red}00{blue}"
    id_range = max_id - min_id
    if id_range:
        norm = (msg.frame_id - min_id) / id_range
    else:
        norm = 0.5

    # higher priority is more red
    out = fmt.format(red=to_hex_str(1-norm), blue=to_hex_str(norm))

    return out

def fmt_msg_name(msg):
    return f"{msg.name}\n{hex(msg.frame_id)} ({msg.frame_id})"

def get_node_names(db: cantools.db.Database):
    return list(set([node.name for node in db.nodes]))

def get_edges(db: cantools.db.Database,
            senders: List[str]=[],
            receivers: List[str]=[]):

    # Sort the messages so they appear in order of increasing CAN ID
    sorted_messages = sort_messages_by_CAN_id(db.messages)

    edges = []
    for sender in senders:
        for receiver in receivers:
            for msg in messages_from_a_to_b(sorted_messages, [sender], [receiver]):
                edges.append((sender, receiver, msg))
    return edges

def dbcview(graph_name: str, edges, output_dir: str):
    """
    display a graph of messages in a DBC
    save to PDF in output dir
    """

    g = Digraph(name=graph_name, filename=graph_name.replace(' ', '_'))

    min_id = min([msg.frame_id for _, _, msg in edges])
    max_id = max([msg.frame_id for _, _, msg in edges])

    for sender, receiver, msg in edges:
        g.edge(tail_name=sender,
               head_name=receiver,
               label=fmt_msg_name(msg),
               color=color_str_for_msg(msg,
                                       min_id=min_id,
                                       max_id=max_id))
  
    g.view(cleanup=True, directory=output_dir)

def main(dbc_filename: str,
         nodes: List[str]=[],
         senders: List[str]=[],
         receivers: List[str]=[],
         ignore: List[str]=[],
         output_dir: str=""):

    db = cantools.db.load_file(dbc_filename)

    all_nodes = get_node_names(db)
    if all_nodes == []:
        print("No nodes found in this DBC!")
        return

    # Check for invalid node names
    nonexistent_nodes = [n for n in nodes + senders + receivers + ignore if n not in all_nodes]
    if nonexistent_nodes:
        print(f"specified nodes: [{', '.join(nonexistent_nodes)}] not found in {dbc_filename}")
        print(f"nodes in this file: [{', '.join(get_node_names(db))}]")
        return

    all_nodes = [n for n in all_nodes if n not in ignore]
    
    """
    If just a list of nodes, assume user wants to see everything into/out of those nodes.
    """ 
    if nodes:
        all_receievers = list(set(nodes + all_nodes))
        all_senders = all_receievers
    elif senders or receivers:
        all_receievers = receivers or all_nodes
        all_senders = senders or all_nodes
    else:
        all_receievers = all_nodes
        all_senders = all_nodes

    edges = get_edges(db, all_senders, all_receievers)
    if not edges:
        print(f"No edges found between {all_senders} and {all_receievers}")

    graph_name = pathlib.Path(dbc_filename).stem
    if set(senders) != set(receivers):
        sender_expr = f"from {' '.join(senders)}" if senders else ""
        receiver_expr = f"to {' '.join(receivers)}" if receivers else ""
        if sender_expr or receiver_expr:
            graph_name += f" {sender_expr} {receiver_expr}"

    output_dir = output_dir if os.path.isdir(output_dir) else tempfile.TemporaryDirectory().name

    dbcview(graph_name, edges, output_dir)

@click.command(short_help="NODES - comma separated list of nodes, Eg MOT,CHG.  Defaults to all")
@click.argument('filename', type=click.Path(exists=True))
@click.argument('nodes', nargs=-1)
@click.option('-s', '--senders', help="comma separated list of sending nodes", default="")
@click.option('-r', '--receivers', help="comma separated list of receiving nodes", default="")
@click.option('-i', '--ignore', help="comma separated list of nodes to ignore", default="")
@click.option('-o', help="Output dir for PDF (defaults to tmp)", default='', type=click.Path())
def cli(filename, nodes, senders, receivers, ignore, o):
    main(filename,
        list(nodes),
        senders.split(',') if senders else [],
        receivers.split(',') if receivers else [],
        ignore.split(',') if ignore else [],
        o)

if __name__ == '__main__':
    cli()
