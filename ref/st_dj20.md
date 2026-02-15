短:=100*(C-LLV(L,3))/(HHV(C,3)-LLV(L,3));
长:=100*(C-LLV(L,21))/(HHV(C,21)-LLV(L,21));
TJ1:=NOT(INBLOCK('创业板') OR INBLOCK('科创板'));
XG:长>=70 AND 长-短>=20 AND TJ1;
