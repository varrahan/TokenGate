"""Compile the existing exact HTTP/2 request-name policy to a fixed BRAM trie."""
import argparse
import hashlib
from pathlib import Path

NAMES={b':method':1,b':scheme':2,b':path':3,b':authority':4,b'content-type':5,b'te':6,b'content-length':7,
       b'grpc-encoding':8,b'grpc-timeout':9,b'host':10,b'connection':11,b'proxy-connection':11,
       b'keep-alive':11,b'transfer-encoding':11,b'upgrade':11}


def image():
    nodes=[{'edges':{},'terminal':0}]
    for name,code in sorted(NAMES.items()):
        node=0
        for octet in name:
            if octet not in nodes[node]['edges']:
                nodes[node]['edges'][octet]=len(nodes);nodes.append({'edges':{},'terminal':0})
            node=nodes[node]['edges'][octet]
        assert nodes[node]['terminal']==0;nodes[node]['terminal']=code
    assert len(nodes)<=128
    words=[0]*256;edges=[]
    for index,node in enumerate(nodes):
        children=sorted(node['edges'].items());assert len(children)<16
        words[index]=len(edges)|(len(children)<<7)|(node['terminal']<<11)
        edges.extend(octet|(child<<8)for octet,child in children)
    assert len(edges)<=128
    words[128:128+len(edges)]=edges
    # Validate the generated data using an independent linear tree walker.
    for name,expected in NAMES.items():
        node=0
        for octet in name:
            first=words[node]&127;count=(words[node]>>7)&15
            choices=[words[128+e]for e in range(first,first+count)]
            found=[w for w in choices if w&255==octet];assert len(found)==1
            node=(found[0]>>8)&127
        assert (words[node]>>11)&15==expected
    return words,len(nodes),len(edges)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'rtl/http2_name_classifier.v')
    args=parser.parse_args();words,nodes,edges=image()
    digest=hashlib.sha256(b''.join(w.to_bytes(2,'little')for w in words)).hexdigest()
    source=args.output.read_text();begin='        // BEGIN_NAME_ROM\n';end='        // END_NAME_ROM'
    prefix,remaining=source.split(begin,1);_,suffix=remaining.split(end,1)
    generated=f'        // {nodes} nodes/{edges} sorted edges; image SHA256 {digest}\n'
    generated+=''.join(f"        words[8'd{index}]=16'h{value:04x};\n"for index,value in enumerate(words)if value)
    args.output.write_text(prefix+begin+generated+end+suffix)
    print(f'Generated fixed HTTP/2 name ROM: {nodes} nodes/{edges} edges/512 bytes, SHA256 {digest}')


if __name__=='__main__':main()
