"""Passive assertions binding formal AXIS assumptions to actual production pins."""


def input_promise_assertions():
    instances=('dut.core.receive_wire','dut.core.local_error_wire','dut.core.refusal_wire',
        'dut.core.controls.controls.tx')
    lines=['// REGISTERED_SELECTION_ACTUAL_INPUT_PROMISE_ASSERTIONS']
    for index,instance in enumerate(instances):
        for source in('a','b'):
            tag=f'registered_select_{index}_{source}'
            valid=instance+'.'+source+'_axis_tvalid';ready=instance+'.'+source+'_axis_tready'
            payload='{'+','.join(instance+'.'+source+'_axis_'+n for n in('tdata','tkeep','tlast','tuser'))+'}'
            lines += [f'reg {tag}_held=0;',f'reg [592:0] {tag}_payload;',
                'always @(posedge clk)begin',f'    if(rst){tag}_held<=0;',
                '    else begin',f'        if({tag}_held)begin',
                f'            if(!{valid}||{payload}!=={tag}_payload)',
                f'                $fatal(1,"Actual registered-selection input promise changed: {instance}.{source}");',
                '        end',f'        {tag}_held<={valid}&&!{ready};',
                f'        {tag}_payload<={payload};','    end','end']
    return '\n'.join(lines)+'\n'
