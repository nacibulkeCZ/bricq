# Sourced only for the bricq interactive Bash login.
case $- in
    *i*) ;;
    *) return ;;
esac
printf '\n'
printf ' BBBB   RRRR   III   CCC    QQQ \n'
printf ' B   B  R   R   I   C      Q   Q\n'
printf ' BBBB   RRRR    I   C      Q   Q\n'
printf ' B   B  R R     I   C      Q  QQ\n'
printf ' BBBB   R  RR  III   CCC    QQQQ\n\n'
printf ' BRICQ robot console\n'
printf ' Commands: bricq status | update | logs | rollback | watch\n\n'
/usr/local/bin/bricq status
PS1='bricq@bricq:\w\$ '
