M1:=14;

M2:=28;

M3:=57;

M4:=114;

知行短期趋势线:=EMA(EMA(C,10),10);

知行多空线:=(MA(CLOSE,M1)+MA(CLOSE,M2)+MA(CLOSE,M3)+MA(CLOSE,M4))/4;

RSV:=(CLOSE-LLV(LOW,9))/(HHV(HIGH,9)-LLV(LOW,9))*100;

K:=SMA(RSV,3,1);

D:=SMA(K,3,1);

J:=3*K-2*D;



COND1 := J < 20;
COND2 := C>知行多空线;

COND3 := C<知行短期趋势线;

COND4 := 知行短期趋势线 > 知行多空线;
上影线:= MIN(C,O)-L;
下影线:= H-MAX(C,O);
COND5 := MIN(C,O)-L > H-MAX(C,O) OR ABS(上影线-下影线)<0.1;

剔除科创 := NOT(INBLOCK('科创板'));

剔除北证 := NOT(INBLOCK('北证A股'));

COND6 := 剔除科创 AND 剔除北证;

流通市值:=FINANCE(40)/100000000;

COND7 := 流通市值>50;

XG: COND1 AND COND2 AND COND3 AND COND4 AND COND5 AND COND6 AND COND7;