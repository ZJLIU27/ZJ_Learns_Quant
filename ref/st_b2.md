{参数定义：KDJ默认为9,3,3}
RSV:=(CLOSE-LLV(LOW,9))/(HHV(HIGH,9)-LLV(LOW,9))*100;
K:=SMA(RSV,3,1);
D:=SMA(K,3,1);
J:=3*K-2*D;

{条件1：当日涨幅 > 4%}
ZF:=(CLOSE/REF(CLOSE,1)-1)*100 > 4;

{条件2：当日成交量 >= 前一天的 1.7 倍}
VOL_COND:=VOL >= REF(VOL,1) * 1.1;

{条件3：当日 J 值 <= 65}
J_NOW:=J <= 65;

{条件4：前一天 J 值 < 20 (超跌区域)}
J_PRE:=REF(J,1) < 20;

{最终输出：同时满足所有条件}
XG:ZF AND VOL_COND AND J_NOW AND J_PRE;