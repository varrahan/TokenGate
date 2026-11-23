"""External dynamic-table operations checked against python-hpack HeaderTable."""
import argparse
from pathlib import Path
import random
import struct
from hpack.table import HeaderTable


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    rng=random.Random(20261119);count=0;successes=0;errors=0
    tables=[HeaderTable(),HeaderTable()];tables[1].maxsize=257
    bases=[0x1003,0x8001];caps=[4096,512];sources=[0x700005,0x710005]
    with(args.output/'vectors.txt').open('w',encoding='ascii')as stream:
        def emit(ctx,op,arg=0,name=b'',value=b'',status=0,mode=0,override=None):
            nonlocal count,successes,errors
            table=tables[ctx];count+=1
            before=list(table.dynamic_entries)
            used=sum(32+len(n)+len(v)for n,v in before)
            request=[op,arg,len(name),len(value),sources[ctx],bases[ctx],caps[ctx],table.maxsize,caps[ctx],used,len(before),count*37&65535]
            if override:
                for index,data in override.items():request[index]=data
            if mode==1:request[4]=0x7fffff
            lookup=b'';ln=lv=0;inserted=0
            if status==0:
                if op==0:
                    n,v=table.get_by_index(62+arg);lookup=n+v;ln=len(n);lv=len(v)
                elif op==1:
                    inserted=int(32+len(name)+len(value)<=table.maxsize);table.add(name,value)
                else:table.maxsize=arg
                image=b''.join(struct.pack('<II',len(n),len(v))+bytes(24)+n+v for n,v in table.dynamic_entries)
                result=[0,0,table.maxsize,len(image),len(table.dynamic_entries),inserted,ln,lv];successes+=1
            else:
                image=b'';result=[status,{2:0x31,3:0x52,6:0x63,7:0x64,8:0x64,9:0x63,10:0x64,11:0x63}.get(mode,0),0,0,0,0,0,0];errors+=1
            # Invalid source tests must reach the DUT before any source write;
            # the helper cannot itself write outside physical RAM.
            payload=name+value if op==1 and mode!=1 and status!=3 else b''
            stream.write(' '.join(map(str,request+result+[mode,len(payload),len(image),len(lookup)]))+'\n')
            for data in(payload,image,lookup):stream.write(' '.join(f'{b:02x}'for b in data)+'\n')
        # Exact accounting edges, zero-length names/values, repeated entries,
        # oldest eviction and byte-at-a-time unaligned record displacement.
        for ctx in range(2):
            for maximum in(0,31,32,33,64,257,caps[ctx]):
                emit(ctx,2,maximum)
                for name,value in((b'',b''),(b'x',b''),(b'',b'y'),(b'content-type',b'application/grpc'),(b'x',b'abc')):
                    emit(ctx,1,name=name,value=value)
                    for index in range(len(tables[ctx].dynamic_entries)):emit(ctx,0,index)
            emit(ctx,1,name=b'big',value=b'a'*(caps[ctx]-35))
            emit(ctx,1,name=b'big',value=b'b'*(caps[ctx]-35))
            emit(ctx,0)
            emit(ctx,1,name=b'x',value=b'z'*5000,mode=1)
        for _ in range(700):
            ctx=rng.randrange(2);table=tables[ctx];choice=rng.randrange(10)
            if choice<6:
                n=bytes(rng.randrange(256)for _ in range(rng.randrange(25)))
                v=bytes(rng.randrange(256)for _ in range(rng.choice([0,1,7,8,9,31,63,127,257,1023])))
                emit(ctx,1,name=n,value=v)
            elif choice<8:emit(ctx,2,rng.randrange(caps[ctx]+1))
            elif table.dynamic_entries:emit(ctx,0,rng.randrange(len(table.dynamic_entries)))
            else:emit(ctx,0,status=2)
        # Invalid requests cannot expose stale pointers or previous state.
        emit(0,0,0xffffffff,status=2)
        emit(0,2,4097,status=3)
        emit(0,3,status=1)
        emit(0,0,status=1,override={5:0x7ffff0,6:4096})
        emit(0,0,status=1,override={7:4097})
        emit(0,0,status=1,override={9:1,10:1})
        emit(0,2,4096);emit(0,1,name=b'x',value=b'y',status=3,override={4:bases[0]})
        emit(0,1,name=b'x',value=b'y',status=3,override={4:0x7fffff})
        # Memory faults and corrupted external headers invalidate the context.
        # Recovery explicitly supplies a fresh empty context in the same region.
        for mode,status in((2,4),(3,5),(4,6)):
            tables[0]=HeaderTable();emit(0,1,name=b'header',value=b'value')
            if mode==3:emit(0,1,name=b'new',value=b'data',mode=mode,status=status)
            else:emit(0,0,mode=mode,status=status)
            tables[0]=HeaderTable();emit(0,1,name=b'recovered',value=b'yes');emit(0,0)
        # Fail each independently acknowledged memory phase, including after
        # part of a retained prefix was moved. Every failed context is retired.
        for mode,status in((6,4),(7,5),(8,5),(9,4),(10,5),(11,4)):
            tables[0]=HeaderTable();emit(0,1,name=b'old',value=b'kept-record'*4)
            if mode==11:emit(0,0,mode=mode,status=status)
            else:emit(0,1,name=b'new-name',value=b'new-value'*4,mode=mode,status=status)
            tables[0]=HeaderTable();emit(0,1,name=b'fresh',value=b'context');emit(0,0)
        emit(0,2,4096);emit(0,1,name=b'before-settings',value=b'x'*200)
        emit(0,2,64,override={8:64})
        emit(0,0,status=2)
    print(f'Generated {count} external HPACK table operations: {successes} successes/{errors} errors, two interleaved connection regions')


if __name__=='__main__':main()
