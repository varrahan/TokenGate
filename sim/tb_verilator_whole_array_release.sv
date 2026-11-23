`timescale 1ns/1ps
module tb_verilator_whole_array_release;
    reg clk=0;
    always #5 clk=~clk;
    logic [7:0] row[2:0];
    logic [7:0] matrix[1:0][2:0];
    integer checks=0;
    always @(posedge clk) begin
        for(integer i=0;i<3;i++)row[i]<=8'h10+i;
        for(integer i=0;i<2;i++)
            for(integer j=0;j<3;j++)matrix[i][j]<=8'h40+16*i+j;
    end
    `define CHECK(value, expected) \
        begin checks++;assert((value)===(expected))else \
            $fatal(1,"Whole-array release check %0d: got %0h expected %0h",checks,value,expected);end
    initial begin
        #2;
        force row='{default:8'h00};
        force matrix='{default:'{default:8'h00}};
        repeat(3)@(posedge clk);
        #1;
        for(integer i=0;i<3;i++)`CHECK(row[i],8'h00)
        for(integer i=0;i<2;i++)
            for(integer j=0;j<3;j++)`CHECK(matrix[i][j],8'h00)
        release row;
        release matrix[1];
        @(posedge clk);#1;
        for(integer i=0;i<3;i++)`CHECK(row[i],8'h10+i)
        for(integer j=0;j<3;j++)begin
            `CHECK(matrix[1][j],8'h50+j)
            `CHECK(matrix[0][j],8'h00)
        end
        release matrix;
        @(posedge clk);#1;
        for(integer i=0;i<2;i++)
            for(integer j=0;j<3;j++)`CHECK(matrix[i][j],8'h40+16*i+j)
        force row='{default:8'ha5};
        #1;
        for(integer i=0;i<3;i++)`CHECK(row[i],8'ha5)
        release row[1];
        @(posedge clk);#1;
        `CHECK(row[0],8'ha5)
        `CHECK(row[1],8'h11)
        `CHECK(row[2],8'ha5)
        release row;
        @(posedge clk);#1;
        for(integer i=0;i<3;i++)`CHECK(row[i],8'h10+i)
        assert(checks==33)else $fatal(1,"Incomplete release test");
        $display("WHOLE_ARRAY_RELEASE_PASS checks=%0d",checks);
        $finish;
    end
    initial begin #1000;$fatal(1,"Whole-array release timeout");end
endmodule
