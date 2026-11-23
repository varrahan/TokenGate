`timescale 1ns/1ps
module tb_hpack_huffman;
    logic clk=0,rst=1;always #2 clk=~clk;
    logic [7:0] s_data=0;logic s_keep=0,s_valid=0,s_last=0;logic [15:0] s_user=0;wire s_ready;
    wire [7:0] m_data,error_code;wire m_keep,m_valid,m_last,error_valid,idle;wire [15:0] m_user,error_user;logic m_ready=0,error_ready=0;
    integer encoded[0:65535],expected[0:65535];integer expected_count=0,expected_bad=0,expected_code=0,expected_user=0,received=0;
    integer strings=0,completed=0,valid_strings=0,invalid_strings=0,committed_bytes=0,tentative_bytes=0,eos_errors=0,padding_errors=0,context_errors=0;
    bit stalled=0,error_stalled=0;logic [25:0] held;logic [23:0] held_error;
    hpack_huffman_decoder dut(
        .clk(clk),.rst(rst),.s_data(s_data),.s_keep(s_keep),.s_valid(s_valid),.s_ready(s_ready),.s_last(s_last),.s_user(s_user),
        .m_data(m_data),.m_keep(m_keep),.m_valid(m_valid),.m_ready(m_ready),.m_last(m_last),.m_user(m_user),
        .error_valid(error_valid),.error_ready(error_ready),.error_code(error_code),.error_user(error_user),.idle(idle));
    always @(negedge clk)begin m_ready=$urandom_range(0,3)!=0;error_ready=$urandom_range(0,3)==0;end
    always @(posedge clk)if(!rst)begin
        if(stalled&&(!m_valid||held!=={m_user,m_last,m_keep,m_data}))$fatal(1,"HPACK Huffman output changed under stall");
        stalled=m_valid&&!m_ready;held={m_user,m_last,m_keep,m_data};
        if(error_stalled&&(!error_valid||held_error!=={error_user,error_code}))$fatal(1,"HPACK Huffman error changed under stall");
        error_stalled=error_valid&&!error_ready;held_error={error_user,error_code};
        if(m_valid&&m_ready)begin
            if(m_user!=expected_user)$fatal(1,"HPACK Huffman output context");
            if(m_keep)begin
                if(m_last)$fatal(1,"Huffman did not use separate EOF");
                if(!expected_bad)begin
                    if(received>=expected_count||m_data!=expected[received])$fatal(1,"Huffman mismatch string=%0d byte=%0d got=%0d expected=%0d",strings,received,m_data,expected[received]);
                    committed_bytes++;
                end else tentative_bytes++;
                received++;
            end
            if(m_last)begin
                if(expected_bad||received!=expected_count||m_keep)$fatal(1,"Failed/truncated Huffman string committed");
                valid_strings++;completed++;
            end
        end
        if(error_valid&&error_ready)begin
            if(!expected_bad||error_user!=expected_user||(expected_code!=0&&error_code!=expected_code))$fatal(1,"Wrong Huffman error string=%0d got=%0d expected=%0d bad=%0d",strings,error_code,expected_code,expected_bad);
            case(error_code)1:eos_errors++;2:padding_errors++;3:context_errors++;default:$fatal(1,"Unexpected Huffman error code");endcase
            invalid_strings++;completed++;
        end
    end
    task automatic send(input [7:0] data_value,input bit keep_value,input bit last_value,input [15:0] context_value);
        @(negedge clk);s_data=data_value;s_keep=keep_value;s_last=last_value;s_user=context_value;s_valid=1;
        do @(posedge clk);while(!s_ready);@(negedge clk);s_valid=0;
    endtask
    initial begin:driver
        integer fd,rc,n,k,bad,code,context_number,mode,target;
        repeat(5)@(negedge clk);rst=0;
        fd=$fopen("vectors.txt","r");if(!fd)$fatal(1,"Missing Huffman vectors");
        while(!$feof(fd))begin
            rc=$fscanf(fd,"%d %d %d %d %d %d",n,k,bad,code,context_number,mode);
            if(rc==6)begin
                if(n>65536||k>65536)$fatal(1,"Huffman fixture capacity");
                for(integer i=0;i<n;i++)begin rc=$fscanf(fd,"%d",encoded[i]);if(rc!=1)$fatal(1,"Missing encoded byte");end
                for(integer i=0;i<k;i++)begin rc=$fscanf(fd,"%d",expected[i]);if(rc!=1)$fatal(1,"Missing decoded byte");end
                expected_count=k;expected_bad=bad;expected_code=code;expected_user=context_number;received=0;target=completed+1;
                if(mode&2)send(0,0,0,context_number^16'hffff);
                if(n==0)send(0,0,1,context_number);
                else begin
                    for(integer i=0;i<n;i++)begin
                        send(8'(encoded[i]),1,i+1==n&&!(mode&1),context_number^((mode&4)&&i!=0?1:0));
                        if(i+1<n&&(mode&2))send(0,0,0,context_number^16'hffff);
                    end
                    if(mode&1)send(0,0,1,context_number^((mode&4)?1:0));
                end
                wait(completed==target);wait(idle);@(negedge clk);strings++;
                if(strings%10000==0)begin $display("PROGRESS: %0d HPACK Huffman reference strings",strings);$fflush();end
            end else if(!$feof(fd))$fatal(1,"Invalid Huffman fixture");
        end
        $fclose(fd);
        if(strings<66000||valid_strings<10000||invalid_strings<10000||committed_bytes<100000||eos_errors!=2||context_errors!=1||padding_errors<10000)$fatal(1,"Huffman coverage strings=%0d valid=%0d invalid=%0d bytes=%0d EOS=%0d context=%0d",strings,valid_strings,invalid_strings,committed_bytes,eos_errors,context_errors);
        $display("PASS: HPACK Huffman: %0d strings/%0d valid/%0d invalid, %0d exact committed bytes/%0d tentative discarded bytes; exhaustive short encodings, all symbols, EOS/padding/context errors, explicit EOF, ignored empty beats, stalls and recovery",strings,valid_strings,invalid_strings,committed_bytes,tentative_bytes);$finish;
    end
    initial begin #(64'd2000000000);$fatal(1,"HPACK Huffman timeout state=%0d",dut.state);end
endmodule
